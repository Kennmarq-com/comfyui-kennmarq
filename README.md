# Kennmarq.com for ComfyUI

Mark AI pictures, songs and clips for the EU AI Act as you save them. **Kennmarq.com Mark & Save Image** takes the place of
Save Image and gives every picture an invisible TrustMark watermark and signed, time-stamped C2PA
Content Credentials that say it was made with AI. They're made on your machine: only the manifest
(about 13 KB, never pixels) goes to Kennmarq.com to be signed. Kennmarq.com helps you meet the Act's marking
duty (Art. 50(2)); you stay responsible for your system.

## Set up

1. Install from ComfyUI-Manager (search "Kennmarq.com"), or clone it into `ComfyUI/custom_nodes`
   and install its requirements in ComfyUI's Python:
   `git clone https://github.com/Kennmarq-com/comfyui-kennmarq ComfyUI/custom_nodes/comfyui-kennmarq`, then
   `pip install -r ComfyUI/custom_nodes/comfyui-kennmarq/requirements.txt`.
2. Get a free key at [kennmarq.com](https://kennmarq.com): 1,000 files a month, every feature. Start
   ComfyUI with it in `KENNMARQ_API_KEY`. The key is never a widget: a widget's value is saved in the
   workflow, and the workflow goes into every PNG you share.

Without a key, the node still writes the watermark and the IPTC AI label, and says how to add signed
Content Credentials.

## The nodes

- **Kennmarq.com Mark & Save Image**: PNG, JPEG or WebP.
  - `source`: `auto` reads the graph: a Load Image node means the picture was made from another
    one (`composite`), otherwise `created`.
  - `keep_workflow`: keeps ComfyUI's prompt and workflow in a PNG, as Save Image does, inside the
    signed file. They reveal your prompt; turn it off to leave them out.
  - `safety_check`: `ai-act` or `safe-only` runs the check below before saving; a blocked picture
    isn't written.
  - `model`, `app_name`: recorded in the Content Credentials.
- **Kennmarq.com Mark & Save Audio**: an AUDIO saved as MP3, M4A or WAV, with Kennmarq.com's
  inaudible AudioSeal mark and signed Content Credentials. Five marks per started minute.
- **Kennmarq.com Mark & Save Video**: frames (an IMAGE batch), their frame rate and an optional AUDIO,
  saved as an MP4 with Video Seal in every frame and AudioSeal in the sound. Its `safety_check` reads
  12 frames (two marks each); a blocked frame leaves the clip unsaved. Five marks per started second.
  `visible_label` (or `deepfake`) draws the EU's "AI GENERATED" label on every frame, in English,
  Korean or Chinese, in the corner `label_position` names.
  Songs and clips are marked in Kennmarq.com's cloud, so these two nodes need `KENNMARQ_API_KEY`.
- **Kennmarq.com Safety Check**: screens pictures for sexual content with someone who appears to be a
  child, and with a realistic face (the AI Act's Art. 5 bans), on your machine. Nothing is sent and
  nothing counted. It stops the run on a block, or passes its answers to Mark & Save Image, which then
  leaves blocked pictures unwritten. A risk signal with published error rates, not a guarantee. Its
  models download once (about 2.3 GB), and it needs onnxruntime.

The watermark's model downloads once (65 MB) to `~/.cache/kennmarq/models` (or
`KENNMARQ_MODELS_DIR`). On Windows, where the C2PA library has no build yet, the node makes the
watermark on your machine and the Content Credentials in the cloud.

MIT-licensed.
