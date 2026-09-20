"""DiffusionGemma 26B-A4B on Modal, served by a vLLM built from the structured-reads branch (vllm PR 57250).

Stage 1 (this file): weights on a Volume, an A100-80GB smoke server, then GPU memory snapshots so a cold start
restores a loaded server instead of reloading 52 GB.

  modal run hosting/dgemma_modal.py::download        # weights into the Volume (CPU, once)
  modal serve hosting/dgemma_modal.py                 # dev server; prints the URL
  modal deploy hosting/dgemma_modal.py                # persistent endpoint

Then, locally, the decision layer from the PR's example (plain Python proxy, needs only the tokenizer):
  python examples/structured_server.py --upstream https://<endpoint> --tokenizer google/diffusiongemma-26B-A4B-it --canvas 64

The image installs the vLLM nightly for its compiled kernels, then overlays the Python files of the PR branch after
merging vLLM main and PR 57589 (multimodal support), plus PR 57462's one-line dtype cast applied as a substitution
because it conflicts textually with the branch. Everything the branch changes is Python, so nothing is compiled.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time

import modal

MODEL = "google/diffusiongemma-26B-A4B-it"
BRANCH_REPO = "https://github.com/mmastrac/vllm.git"
BRANCH = "structured-reads-main"
EXTRA_PRS = (57589,)                # open prerequisite merged on top of the branch (multimodal support)
# PR 57462 is one line and conflicts textually with the branch, so it is applied as a substitution instead.
DTYPE_FIX = ("sc_embeds[decode_slots] = soft_embeds * sc_keep", "sc_embeds[decode_slots] = (soft_embeds * sc_keep).to(sc_embeds.dtype)")
CANVAS = 64
PORT = 8000
MINUTES = 60
ATTENTION_BACKEND = "TRITON_ATTN"
SNAPSHOT = False    # GPU memory snapshots: off for the smoke round, on once the server is known good
LOGS = "/weights/logs"   # vLLM output persisted on the Volume; Modal's log viewer keeps only the last ~100 lines

app = modal.App("vladbench-dgemma")
weights = modal.Volume.from_name("vladbench-weights", create_if_missing=True)
WEIGHTS = "/weights"
hf_secret = modal.Secret.from_name("HF_TOKEN")

PATCH = f"""
import pathlib
path = pathlib.Path('/opt/vllm/vllm/model_executor/models/diffusion_gemma.py')
text = path.read_text()
assert text.count({DTYPE_FIX[0]!r}) == 1, 'dtype fix target not found exactly once'
path.write_text(text.replace({DTYPE_FIX[0]!r}, {DTYPE_FIX[1]!r}))
print('dtype fix applied')
"""

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .apt_install("git", "curl", "rsync")
    .pip_install("uv")
    # Layer 1: nightly vLLM for the dependency set and compiled kernels. Cached across edits to the layers below.
    .run_commands("uv pip install --system --pre vllm --extra-index-url https://wheels.vllm.ai/nightly")
    # Layer 2: the PR branch, vLLM main, the multimodal fix, and the one-line dtype fix.
    .run_commands(
        f"git clone --depth 200 --branch {BRANCH} {BRANCH_REPO} /opt/vllm",
        "cd /opt/vllm && git remote add upstream https://github.com/vllm-project/vllm.git && git fetch --depth 200 upstream main"
        " && git -c user.name=build -c user.email=build@local merge --no-edit upstream/main",
        *[f"cd /opt/vllm && git fetch upstream pull/{n}/head:pr{n} && git -c user.name=build -c user.email=build@local merge --no-edit pr{n}" for n in EXTRA_PRS],
        f"python - <<'PY'\n{PATCH}\nPY",
        "cd /opt/vllm && git log --oneline -3",
    )
    # Layer 3: the branch's Python files over the installed nightly, whose compiled kernels stay in place. The branch
    # touches only Python, and it was merged with the same main the nightly was built from, so no build is needed.
    .run_commands(
        "SITE=$(python -c 'import vllm, os; print(os.path.dirname(vllm.__file__))') && echo overlaying onto $SITE"
        " && rsync -a --exclude '*.so' --exclude '__pycache__' /opt/vllm/vllm/ $SITE/",
        "python -c 'import vllm, vllm._custom_ops, vllm.v1.core.sched.diffusion_scheduler as d; print(vllm.__version__, d.__file__)'",
        "grep -c diffusion_seed_canvas /usr/local/lib/python3.12/site-packages/vllm/sampling_params.py",   # the branch's request fields are in place
    )
    .env({"HF_HUB_CACHE": WEIGHTS, "VLLM_LOGGING_LEVEL": "INFO", "HF_HUB_ENABLE_HF_TRANSFER": "0"})
)


@app.function(image=image, volumes={WEIGHTS: weights}, secrets=[hf_secret], timeout=2 * MINUTES * 60)
def download(revision: str | None = None) -> str:
    """Snapshot the weights into the Volume; returns the resolved revision."""
    from huggingface_hub import snapshot_download

    path = snapshot_download(MODEL, revision=revision, allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "scheduler/*"])
    weights.commit()
    return path


@app.function(image=image, gpu="A100-80GB", timeout=10 * MINUTES)
def inspect_build() -> dict:
    """What the image actually holds: compiled ops present, branch files present, GPU visible."""
    import glob
    import importlib
    import os
    import torch
    import vllm
    site = os.path.dirname(vllm.__file__)
    out = {"vllm": vllm.__version__, "so": sorted(os.path.basename(f) for f in glob.glob(site + "/*.so")),
           "cuda": torch.cuda.is_available(), "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}
    for name in ("vllm._C", "vllm._custom_ops", "vllm.v1.core.sched.diffusion_scheduler", "vllm.model_executor.models.diffusion_gemma"):
        try:
            importlib.import_module(name); out[name] = "ok"
        except Exception as error:   # noqa: BLE001
            out[name] = f"{type(error).__name__}: {error}"[:200]
    return out


@app.cls(
    image=image,
    gpu="A100-80GB",
    volumes={WEIGHTS: weights},
    secrets=[hf_secret],
    timeout=MINUTES * 60,
    scaledown_window=10 * MINUTES,
    enable_memory_snapshot=SNAPSHOT,
    experimental_options={"enable_gpu_snapshot": SNAPSHOT},
)
@modal.concurrent(max_inputs=64)
class Server:
    """vLLM's OpenAI server on the PR build. The process is started in the snapshotting phase, so restores
    come back with the model already on the GPU."""

    @modal.enter(snap=SNAPSHOT)
    def start(self):
        cmd = [
            "vllm", "serve", MODEL,
            "--served-model-name", "dgemma", MODEL,
            "--host", "0.0.0.0", "--port", str(PORT),
            "--max-model-len", "8192",
            "--diffusion-config", '{"canvas_length": %d}' % CANVAS,
            "--max-logprobs", "32",
            "--enable-prefix-caching",
            "--gpu-memory-utilization", "0.90",
            # DiffusionGemma passes a per-request causal tensor (prompt encoding is causal, denoise steps are not).
            # FlashInfer cannot take that and is what one attention group falls back to on the A100, where
            # FlashAttention 2 caps the head size at 256. Triton handles both groups. Hopper and Blackwell get
            # FlashAttention 3 and 4, so this override can go once the server moves to a bigger GPU.
            "--attention-backend", ATTENTION_BACKEND,
        ]
        os.makedirs(LOGS, exist_ok=True)
        self.log_path = f"{LOGS}/serve-{time.strftime('%Y%m%d-%H%M%S')}.log"
        # tee: the output still reaches Modal's viewer, and the full text survives on the Volume.
        self.proc = subprocess.Popen(f"exec {' '.join(map(shlex.quote, cmd))} 2>&1 | tee {self.log_path}", shell=True, env={**os.environ})
        deadline = time.time() + 30 * MINUTES
        import urllib.request
        last_commit = 0
        while time.time() < deadline:
            if time.time() - last_commit > 60:
                weights.commit(); last_commit = time.time()
            if self.proc.poll() is not None:
                weights.commit()
                raise RuntimeError(f"vllm exited with {self.proc.returncode} during startup; log at {self.log_path}")
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2)
                weights.commit()
                print("vllm healthy; log at", self.log_path)
                return
            except Exception:
                time.sleep(3)
        weights.commit()
        raise RuntimeError("vllm did not become healthy in time")

    @modal.web_server(PORT, startup_timeout=30 * MINUTES)
    def serve(self):
        pass

    @modal.exit()
    def stop(self):
        if getattr(self, "proc", None) and self.proc.poll() is None:
            self.proc.terminate()
        try:
            weights.commit()
        except Exception:   # noqa: BLE001
            pass


@app.local_entrypoint()
def check():
    """Print what inspect_build finds on a GPU worker."""
    import json
    print(json.dumps(inspect_build.remote(), indent=1))


@app.local_entrypoint()
def smoke():
    """Probe a deployed or served endpoint: one text and one image request through the raw OpenAI route."""
    import base64
    import io
    import json
    import urllib.request

    from PIL import Image

    url = Server().serve.get_web_url()
    print("endpoint", url)
    image = Image.new("RGB", (640, 360), (220, 30, 30))
    buffer = io.BytesIO(); image.save(buffer, format="JPEG")
    data = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    for content in ("Say the word ready.", [{"type": "image_url", "image_url": {"url": data}}, {"type": "text", "text": "What colour is this image? One word."}]):
        body = {"model": "dgemma", "messages": [{"role": "user", "content": content}], "max_tokens": 16}
        request = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(), headers={"content-type": "application/json"})
        started = time.time()
        with urllib.request.urlopen(request, timeout=600) as response:
            reply = json.load(response)
        print(f"{time.time() - started:5.1f}s", json.dumps(reply["choices"][0]["message"]["content"]), reply.get("usage"))
