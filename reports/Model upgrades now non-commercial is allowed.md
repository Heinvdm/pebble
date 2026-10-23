# Model upgrades now non-commercial is allowed

Survey of 19 October 2026, after two owner decisions that day:
- Pebble is never sold, so non-commercial models may be used: "make it as good as we can with what's available."
- The Pixel 6 Pro is the floor: every feature must run well on it, alongside everything else, and a stronger phone picks a higher rung by measuring itself.

**Owner's answers (19 October 2026):**
1. MobileCLIP2: yes, used on the PC only; what it helps make is built locally and kept out of the public repo.
2. InsightFace: yes, fetched at setup and never tracked; SFace built alongside as the fallback.
3. FUTO asr4all: no. Its ban on "bulk or untargeted … transcription" reads close to always-on listening. Try Moonshine v2 (MIT) against NeMo instead; voice prints stay.
4. Kitten TTS is the Pixel's floor voice if Kokoro is too slow; Kokoro on stronger phones.

**The short answer.** Allowing non-commercial licences changes less than expected. It matters in three places:
- the words the object and hazard models look for (Apple's MobileCLIP2 makes them);
- face prints (InsightFace's models);
- the bigger depth models, which are too slow for the moving floor scan anyway.

Most of the real gains come from newer permissive models released since the parts were picked: sound events, voice activity, voice prints, the main model's 4-bit file and the person detector.

**How sure this is.** Nothing has run on the Pixel 6 Pro yet. Every phone speed below is an estimate, scaled from published phone, Raspberry Pi or PC numbers. Each "try" in the table means: measure it on the phone, with everything else running, before switching.

## Ranked changes (biggest gain for the robot first)

| # | Job | Change | Licence | What it gains | Cost on the Pixel 6 Pro (est.) | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Face prints (who someone is) | Build them on InsightFace's ArcFace R50 (`w600k_r50`) | Non-commercial research only | Pebble can know people by sight at all. InsightFace's hard multi-race test: 91.3 % against 71.9 % for its small model; IJB-C 97.3 % | 0.2–0.4 s a print, only when a new face appears; about 170 MB | **Switch** (build), after owner decision 2 |
| 2 | Objects (slow lane) | YOLOE-26n with text prompts and a hand-picked home word list | AGPL-3.0, plus Apple's research-only terms on the PC side | LVIS 16.6 → 24.7 at about the same cost; words the built-in list lacks ("pet bowl", "power strip") | Same as today, 230–300 ms a look | **Switch**, after owner decision 1 |
| 3 | Sound events | CED-Tiny or CED-Mini (already packaged for sherpa-onnx) | Apache-2.0 weights | AudioSet mAP 0.306 → 0.481 / 0.490 (YAMNet against CED) | Small; not published | **Try and measure** |
| 4 | People and animals (fast lane) | First find why NanoDet is slow here; then YOLO26n at 416, or NanoDet-Plus-1.5x | AGPL-3.0 (already accepted) / Apache-2.0 | COCO AP 30.4 → 40.9 (YOLO26n, at 640) or 34.1 | 30–50 ms a run at 416 | **Try and measure**; today's NanoDet stays the safety floor |
| 5 | Main model | Gemma 4 E4B's official QAT 4-bit checkpoint instead of today's Q4_K_M; keep the prompt cache warm; try its drafter model; A/B Qwen3.5-4B | Apache-2.0 | Same model, closer to full quality at 4 bits; Unsloth's QAT-based file is 4.22 GB against 4.98 GB | Same or less | **Switch** the file; **try** the rest |
| 6 | Voice activity | Silero VAD v6 (today's file is k2-fsa's v4 export) | MIT | Fewer false starts from household noise: noise-only accuracy 0.51 → 0.87 on ESC-50 (Silero's own tests) | Same | **Switch**, after a load and replay test |
| 7 | Hazards | YOLOE-26s with text prompts (`export_hazards.py --mode text`, already written) | AGPL-3.0, plus Apple's terms | LVIS 21.4 → 30.8; on our 17 photos: as good on fire, one more smoke found | Same as today | **Switch**, after decision 1 and re-running the photo checks |
| 8 | Body points and posture | RTMPose-s (body7, or the Halpe-26 set with feet); MediaPipe BlazePose Full as a second opinion for "lying on the floor" | Apache-2.0 | COCO keypoint AP 65.9 → 69.7; feet help tell sitting from crouching | 15–30 ms a person | **Switch** RTMPose-s after the posture checks; **try** BlazePose |
| 9 | Object and place prints | DINOv3 ViT-S/16 | DINOv3 Licence (gated download, banned uses) | Finding the same thing again (Oxford-Hard) 39.5 → 49.5, same size | Same or less | **Try and measure** |
| 10 | Speech recognition | FUTO asr4all-M (streaming) | FUTO licence with field-of-use bans | Published AMI 11.2 %; 7.6 times faster than real time on one Pixel 4 core, so about 13 % of a core against today's 40–80 % | Much cheaper; slower to commit words (0.92 s floor against 0.48 s) | **Try and measure**, after owner decision 3 |
| 11 | Pebble's voice | Measure Kokoro under load before building on it; Kitten TTS as the floor voice if Kokoro is slower than about 0.6 of real time | Apache-2.0 (sherpa's Kokoro pulls in GPL-3.0 espeak-ng) | Keeps speech from stalling: Kokoro is likely 1–2 times slower than real time here under load | — | **Try and measure** |
| 12 | Picture understanding | Keep Gemma 4's own vision; set its picture budget to 70 or 140 tokens (`--image-max-tokens`) | Apache-2.0 | About 1–3 s a picture instead of 4–6 s at 280 tokens | Less | **Switch** (a setting) |
| 13 | Name spotting | Train a "Pebble" model with livekit-wakeword and use it alongside today's spotter | Apache-2.0 | Its authors' test: 0.08 false fires an hour and 86 % found, against 8.5 and 69 % for openWakeWord; aimed at the slow male voice it misses | A few % of a small core | **Try and measure** |
| 14 | Voice prints | WeSpeaker ResNet34-LM (in sherpa today), then ReDimNet2-B2 | CC-BY-4.0 / MIT code | VoxCeleb1-O error rate 1.15 % → 0.72 % / 0.57 % | Tens of ms a turn | **Try and measure** |
| 15 | Small model | LFM2.5-350M | LFM Open License | IFEval 71.7 → 77.0, Multi-IF 37.7 → 44.9 | About 0.4 GB; 10–20 tokens/s on two small cores | **Try and measure** |
| 16 | Floor depth | Keep Depth Anything V2 Small; try Distill Any Depth Small (same size); V2 Base only for still scans or stronger phones | Apache-2.0 / MIT / CC-BY-NC-4.0 | Base: indoor error (NYU AbsRel) 0.053 → 0.049 | Base: 1.1–1.8 s a scan | **Keep** |
| 17 | Face detection | Keep YuNet; run it at 640 wide, or on head crops from the body points | MIT | Finds farther faces | Small | **Keep** |

## Decisions for the owner

1. **Apple's MobileCLIP2 terms** (rows 2 and 7). They allow only "non-commercial scientific research and academic development", which is narrower than plain non-commercial. A personal robot is non-commercial, but it is not obviously research. MobileCLIP2 would run only on the PC, once, to turn the word lists into numbers; the phone carries the numbers, never the model. The terms don't say whether those numbers count as a derivative. FastVLM (Apple, same terms) is not recommended anyway.
2. **InsightFace's terms** (row 1). Its models and training data are "non-commercial research purposes only", the same research question as Apple's. Since November 2025 its README also asks people to contact it about licensing the `buffalo_l` pack, which holds the R50. If no: build face prints on OpenCV's SFace (Apache-2.0), which is weaker.
3. **FUTO's asr4all bans** (row 10). They forbid, among other things:
   - "building or searching a database of voiceprints in order to identify or track people";
   - covert interception of conversations you aren't part of.

   Pebble transcribes talk it isn't part of (the overheard mode, with the ears mark showing) and keeps voice prints (made by a different model). It isn't covert and nothing leaves the phone, but this is the owner's reading to make. If no: keep NeMo and look at NVIDIA's Parakeet end-of-utterance model.
4. **Choose the print models before anyone is enrolled.** Face, voice and thing prints from different models can't be compared. Each change means taking every print again, from people and things, inside a sealed self. Nothing has been enrolled on the phone yet, so now is the cheap time.
5. **The voice plan (plan section 6, step 2).** If Kokoro is too slow under load, may Kitten TTS be the Pixel's voice, with Kokoro on stronger phones? Pebble's voice would be kept the same across both by training the small model on the PC, overnight, on lines spoken in the evolved voice.
6. **espeak-ng (GPL-3.0)** sits inside sherpa-onnx's Kokoro. Pebble already carries AGPL-3.0 parts, and GPL-3.0 and AGPL-3.0 are compatible, so publishing the source covers both. An espeak-free front end exists in the LiteRT port of Kokoro if that is preferred.
7. **DINOv3 is a gated download** (row 9). Someone must accept Meta's terms on a Hugging Face account, so the fetch script can't fetch it anonymously; the made-here ONNX file would be tracked like `prints.onnx`.

## How a phone picks its rung

Today the eyes time each model alone, on one sample picture, and keep the fastest backend (`android/app/.../eyes/Bench.kt`). The ladder needs more than that:

1. **Time under load.** Time each candidate rung while the others run at their real rates: a short llama.cpp decode, the fast lane, the ASR on a looped recording. Warm up for a few minutes first, then measure for about a minute.
2. **Use the slow end, not the average.** Keep the 95th-percentile time against the job's budget.
3. **Check the answers, not just the speed.** Run a bundled golden picture or recording per backend and compare with the PC's output: boxes, rays, transcripts, a print vector to within cosine 0.99. GPU, NPU and fp16 paths can return wrong results silently.
4. **Memory and heat.** Check free memory after loading, and Android's thermal status and headroom before and after.
5. **Remember the choice.** Store it per phone and app version, and redo it on "measure again".
6. **Step down at run time.** Drop a rung when the budget is missed several times in a row, at thermal "moderate" or worse, or on a backend error. Climb back only after a cool-down. A step up can then never make Pebble worse.
7. **Print models are the exception.** Face, voice and thing prints are chosen once per phone and never switched by themselves; a faster phone just prints more often.

## Floor depth (the floor scan)

**Today.** Depth Anything V2 Small (Apache-2.0, 24.8M parameters).
- It runs fp16 at 238 x 182 on the plain CPU (XNNPACK refuses its Resize step).
- Estimate: 300–450 ms a scan with two threads, so 2–3 scans a second while moving.

**What the licence change opens: V2 Base (97.5M) and Large (335M), both CC-BY-NC-4.0.** The paper's own numbers:

| | Small | Base | Large |
| --- | --- | --- | --- |
| Indoor rooms, NYU-D error (AbsRel, lower is better) | 0.053 | 0.049 | 0.045 |
| DA-2K, which of two points is nearer | 95.3 % | 97.0 % | 97.1 % |
| Work, against Small | 1x | about 4x | about 13x |
| Pixel 6 Pro, per scan (est.) | 0.3–0.45 s | 1.1–1.8 s | 4–6 s |

So Base makes about 8 % fewer depth errors indoors, but drops the scan to under one a second; Large to one every 4–6 s. That is worse for a robot that moves. The faults measured so far wouldn't be fixed by an 8 % smaller depth error:
- a 20 cm step seen 0.5 m late: a viewing-angle problem at 14 cm;
- a 1.2 cm cable never seen: it has no height for any depth model to see.

**Other options:**
- **Distill Any Depth Small** (MIT, the same 24.8M architecture, distilled from larger teachers). It is a file swap at the same speed. Its paper shows its distillation cutting a Small student's error by about 10 % on DIODE and ETH3D, but there is no head-to-head with the released V2 Small. Free to try.
- **Depth Anything 3 Small and Base** (Apache-2.0, 0.08B and 0.12B). They are made for many views and camera poses. The authors claim better single-picture depth than V2, but give no Small-against-Small numbers. A LiteRT conversion of DA3 Small takes 3.9 s on a Pixel 8a CPU at 896 x 504. No.
- **Video Depth Anything Small** (Apache-2.0). Steadier depth over time, but its streaming mode loses accuracy (ScanNet delta1 0.926 → 0.836, in the authors' note), and Base/Large are non-commercial. No.

**Ladder:**
- **Pixel 6 Pro:** V2 Small at 238 x 182 on the CPU for the moving scan, or Distill Any Depth Small if it beats it on the drawn rooms and the nine photos. Try V2 Base only as a one-off careful look when Pebble is stopped and about to set off, or when a Small scan scores low. It must earn its place on the step-down and clutter rooms.
- **Stronger phone:** Small at 308 x 238 on a GPU or NPU path (Qualcomm packages V2 Small for its NPUs; search results showed profile runs of about 50–60 ms at 518 x 518 on Snapdragon 8 Gen 3 and 8 Elite, which I could not open to confirm). Then Base once it measures 3 or more scans a second with everything else running.
- **Measure:** ms per scan on each backend that loads, with the fast lane and a llama.cpp prompt running; the rays on the bundled drawn rooms against the PC's; memory. Fall back to Small on the CPU if a scan takes over 0.5 s or the phone reaches "moderate".

**Verdict:** keep V2 Small; try Distill Any Depth Small; Base only for still scans or stronger phones; Large no.

Sources: [Depth Anything V2 (sizes, licences)](https://github.com/DepthAnything/Depth-Anything-V2), [V2 paper tables](https://arxiv.org/html/2406.09414), [Distill Any Depth](https://github.com/Westlake-AGI-Lab/Distill-Any-Depth), [its Small model card (MIT)](https://huggingface.co/xingyang1/Distill-Any-Depth-Small-hf), [its paper](https://arxiv.org/html/2502.19204), [Depth Anything 3](https://github.com/ByteDance-Seed/Depth-Anything-3), [DA3 Small on LiteRT](https://huggingface.co/litert-community/Depth-Anything-3-Small), [Metric Video Depth Anything Small](https://huggingface.co/depth-anything/Metric-Video-Depth-Anything-Small/blob/main/README.md), [Qualcomm AI Hub, V2 Small](https://aihub.qualcomm.com/models/depth_anything_v2).

## Objects (the slow lane)

**Today.** YOLOE-26n prompt-free (AGPL-3.0), cut to 2,010 of its own built-in words, at 416 px.
- About 230–300 ms a look on one thread (estimate).
- At most once a second, only when the picture changed.

**What the licence change opens: YOLOE's text-prompt mode.** You write the words; MobileCLIP2 turns them into numbers once, on the PC. They are baked into the ONNX file (`set_classes`, then export; the classes are then fixed). Nothing of Apple's runs on the phone. Ultralytics' table (LVIS, 640 px, mAP 50–95):

| Model | Prompt-free | Text prompts |
| --- | --- | --- |
| YOLOE-26n | 16.6 | 24.7 (+8.1) |
| YOLOE-26s | 21.4 | 30.8 (+9.4) |
| YOLOE-26m | 25.7 | 35.4 |

- The text-prompt nano's backbone is about 15 % more work (6.1 against 5.3 GFLOPs).
- The class head grows with the number of words. A hand-picked list of 500–1,000 home words should cost less than today's 2,010, not more (my estimate; measure it).
- Words the built-in list lacks become possible: "pet bowl", "power strip", "extension lead".
- `tools/export_objects.py` has no text mode yet; `export_hazards.py` shows how.

**Licence:** see owner decision 1.

**Ladder:**
- **Pixel 6 Pro:** YOLOE-26n with text prompts at 416 px, on today's schedule.
- **Stronger phone:** 26s text at 416; then 26s or 26m text at 640 on a GPU or NPU, looking every 0.5 s.
- **Measure:** ms per look under load. Step up while the next rung stays under about 250 ms. Every rung uses the same word list, so the brain sees the same names whichever runs.

**Verdict:** switch to text prompts once decision 1 is made. Check the curated list on the desk, cat and teapot photos and a set of home photos first.

Sources: [Ultralytics YOLOE (tables, text encoder, export)](https://docs.ultralytics.com/models/yoloe/), [Apple MobileCLIP and its model terms](https://github.com/apple/ml-mobileclip), [the terms themselves](https://github.com/apple/ml-mobileclip/blob/main/LICENSE_MODELS).

## Hazards (fire, smoke, cables)

**Today.** YOLOE-26s prompt-free, cut to 21 built-in words.
- It looks every 3 s, and every 0.8 s during a close watch; about 310–420 ms a look (estimate).
- On 17 photos it found 4 fires, missed 2 fires and a forest fire's smoke, and raised no false alarm at 0.5.

**What the licence change opens: the same text-prompt mode.** `tools/export_hazards.py --mode text` already makes it.
- When it was tried, it was about as good on fire and found smoke in one more photo. It was set aside only for the licence.
- LVIS for 26s: 21.4 → 30.8.
- It allows heat words the built-in list lacks: "space heater", "clothes iron", "hair straightener", "electrical sparks".
- Cables stay hard. No model reliably sees a 1 cm cable from 14 cm. The object list can carry "cable on the floor" and "power cord", which already cut the floor rays.

**Other options:** published fire and smoke detectors are almost all YOLO fine-tunes (AGPL) on outdoor and wildfire pictures, with dataset licences that disagree between sources. I found none checked against indoor lookalikes. Training our own head on D-Fire later is possible; it is not a swap.

**Ladder:**
- **Pixel 6 Pro:** 26s text with about 30 fire, smoke, heat and lookalike words, at 416 px, on today's schedule. As the alarm ladder's "re-check" step, Gemma 4 can also be asked about a snapshot (the picture path exists).
- **Stronger phone:** 26m text at 640 on a GPU or NPU, looking every 1 s.
- **Measure:** the hazard look must stay under about 400 ms with everything else running.

**Verdict:** switch to `--mode text` (decision 1), after re-running the 17 photos and the lookalike checks.

Sources: [Ultralytics YOLOE](https://docs.ultralytics.com/models/yoloe/), [D-Fire licence as reported in a 2025 paper](https://arxiv.org/pdf/2503.14552), [a D-Fire mirror listing CC BY 4.0](https://universe.roboflow.com/uweeaai/d-fire-ehbj2); our own photo results are in `brain/README.md`.

## People and posture

**Today.**
- **People and the 80 COCO things:** NanoDet-Plus-m 416 (Apache-2.0, 30.4 COCO AP). 45–60 ms on the PC through OpenCV.
- **Body points:** RTMPose-t (Apache-2.0, 65.9 AP), up to 3 people, 5 times a second.

**Look at the runtime first.** NanoDet-Plus-m 416 is published at 19.8 ms on a Kirin 980's four A76 cores (ncnn), and RTMPose-t at 9 ms on a Snapdragon 865. Pebble's PC timings and phone estimates are several times slower. Profile the pre- and post-processing and the runtime before buying a bigger model: that gap may be worth more than any swap below.

**People and animals:**
- **NanoDet-Plus-m-1.5x 416** (Apache-2.0). 34.1 AP at 2.97 GFLOPs; a drop-in swap. 20–40 ms (est.).
- **YOLO26n** (AGPL-3.0, already accepted).
  - 40.9 AP at 640, 5.5 GFLOPs, no NMS step.
  - Its accuracy at 416 is not published.
  - Plain CNN, so it suits XNNPACK and NPUs.
  - 30–50 ms at 416 (est.).
- **D-FINE-N / DEIM-N** (Apache-2.0, about 43 AP). Their deformable attention suits phone CPUs badly. No.
- **DEIMv2** (its own licence; commercial use by contact). No better per unit of work.
- **RF-DETR-N** (48 AP, but about 32 GFLOPs). No for the fast lane.

**Posture:**
- **RTMPose-s** (Apache-2.0). 69.7 AP at 0.68 GFLOPs; 15–30 ms a person (est.).
- **RTMPose Halpe-26** (Apache-2.0). Adds head, neck and six foot points, which help with sitting, crouching and lying. The posture rules would need re-tuning.
- **MediaPipe BlazePose Full** (Apache-2.0). 33 points plus 3D "world" points in metres, and a detector that turns the crop to the body's tilt, which suits someone lying down. Try it as a second opinion for "lying on the floor".
- **RTMPose-m** (74.9 AP) and **RTMW** (hands too, for held things and pointing) are higher rungs.
- **Sapiens** (CC-BY-NC-4.0; 0.3B parameters, 1.2 TFLOPs) can't run on a phone.
- None of these models publishes accuracy on fallen or lying people. That must be tested on our own clips.

**Ladder:**
- **Pixel 6 Pro:** NanoDet-Plus-m as the guaranteed safety floor. Promote YOLO26n at 416 (or NanoDet 1.5x) if it measures fast enough. RTMPose-s at 5 Hz, with BlazePose Full at a low rate for lying checks.
- **Stronger phone:** YOLO26n, then YOLO26s (48.6 AP), at 640 on an NPU; Qualcomm lists YOLO11n at 640 at 1–4 ms on the Snapdragon 8 Gen 3 NPU. RTMPose-m Halpe-26 at 10 Hz; RTMW for hands.
- **Measure:** median and 95th-percentile time with every other lane running, after a 5-minute warm-up; a golden-picture check of the boxes on each backend. The safety lane never falls below its floor rate.

**Verdict:** profile first; try YOLO26n and NanoDet 1.5x; switch to RTMPose-s after the posture checks; try BlazePose for lying.

Sources: [NanoDet](https://github.com/RangiLyu/nanodet), [YOLO26](https://docs.ultralytics.com/models/yolo26/), [YOLO26 pose](https://docs.ultralytics.com/tasks/pose/), [D-FINE](https://github.com/Peterande/D-FINE), [DEIMv2](https://github.com/Intellindust-AI-Lab/DEIMv2), [RF-DETR](https://github.com/roboflow/rf-detr), [RTMPose](https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose), [Qualcomm YOLO11 on NPU](https://huggingface.co/qualcomm/YOLOv11-Detection), [Qualcomm RTMPose](https://huggingface.co/qualcomm/RTMPose-Body2d), [BlazePose docs (mirror)](https://cdn.jsdelivr.net/npm/@subhajit-gorai/react-native-mediapipe-llm@1.0.3/mediapipe/docs/solutions/pose.md), [ML Kit pose model card](https://developers.google.cn/static/ml-kit/images/vision/pose-detection/pose_model_card.pdf), [Sapiens](https://huggingface.co/facebook/sapiens-pose-0.3b-torchscript).

## Faces and face prints

**Face detection today:** YuNet (MIT) at 320 px wide.
- How big a face is: with the Pixel's front camera (about 81° across), a face is about 28 pixels wide at 2 m and 19 at 3 m in a 640-wide picture, and half that at 320. That is at YuNet's lower limit.
- **Keep YuNet, but feed it better:** run it at 640, or on head crops cut from the body points' nose, eyes and ears, which costs almost nothing. The lip reading depends on its five landmarks.
- **SCRFD-2.5G** (InsightFace; code MIT, weights non-commercial research only) scores 77.1 on WIDER FACE "hard", against about 0.71–0.75 for YuNet. It is a higher rung if YuNet misses far faces.

**Face prints today:** not built. `people/prints.py` is a seam that returns no prints.

| Model | Licence | IJB-C (TAR at FAR 1e-4) | Hard multi-race test (MR-ALL) | Work per face | Pixel 6 Pro (est.) |
| --- | --- | --- | --- | --- | --- |
| SFace (OpenCV Zoo) | Apache-2.0 (training data not stated) | not published | not published | small | under 30 ms |
| `w600k_mbf` (buffalo_s) | Non-commercial research | 95.0 | 71.9 | 0.45 GFLOPs | 20–30 ms |
| `w600k_r50` (buffalo_l) | Non-commercial research | 97.3 | 91.3 | 6.3 GFLOPs | 0.2–0.4 s |
| ArcFace ViT-T, WebFace42M | Non-commercial research (download not confirmed) | 97.3 | 92.0 | 1.5 GFLOPs | 60–100 ms |
| EdgeFace-S | CC-BY-NC-SA-4.0 (share-alike), PyTorch only | 95.6 | — | 0.3 GFLOPs | 20–30 ms |
| LVFace-T | Non-commercial research, ONNX released | 96.7 | — | not stated | — |

- Every ArcFace-family model is trained on research-only face data (MS1M, Glint360K, WebFace), so its weights are research-only whatever the code's licence says.
- The hard multi-race test is where the big gap is: 91 against 72.
- The phone times are my estimates: R50 is about 2.6 times the work of the DINOv2 print, which is estimated at 95–145 ms.

**Making good prints from small faces:**
- Print only when a new face track appears, at most once or twice a second, and only from faces big and sharp enough.
- Take the crop from a bigger frame: CameraX can give a 1280 x 960 frame, as the rear camera already uses.
- Average several frames.
- Store a model tag with every print.
- Set the 0.82 match threshold again for the chosen model; it belongs to no model today.

**Ladder:**
- **Pixel 6 Pro:** R50 (or ViT-T if it can be had) at a low rate.
- **Stronger phone:** the same model on a GPU or NPU, printing more often. Never switch models by itself (decision 4).
- **Measure:** ms per print, and a bundled face's print against the PC's to within cosine 0.99. Fall back to the CPU, never to another model.

**Verdict:** build face prints on `w600k_r50` if decision 2 is yes, otherwise on SFace.

Sources: [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), [SCRFD](https://github.com/deepinsight/insightface/tree/master/detection/scrfd), [InsightFace README (terms, 2025 licensing note)](https://github.com/deepinsight/insightface), [InsightFace model zoo](https://github.com/deepinsight/insightface/tree/master/model_zoo), [arcface_torch results](https://github.com/deepinsight/insightface/tree/master/recognition/arcface_torch), [SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface), [EdgeFace](https://github.com/otroshi/edgeface), [LVFace](https://github.com/bytedance/LVFace), [WebFace260M terms](https://arxiv.org/pdf/2103.04098).

## Voice prints

**Today.** TitaNet-S (192 numbers, 6.4M parameters). VoxCeleb1-O error rate 1.15 %; our own tests: 4.4 % at 1.5 s and 12 % on far meeting talk.

| Model | Licence | VoxCeleb1-O EER | Size / work | Runs in |
| --- | --- | --- | --- | --- |
| WeSpeaker ResNet34-LM | CC-BY-4.0 (VoxCeleb) | 0.72 % | 26.5 MB | sherpa-onnx today |
| ReDimNet2-B2 | MIT code; weights' licence not stated | 0.57 % | 3.6M, 0.95 GMACs per 2 s | needs our own ONNX export and filterbank |
| TitaNet-L | CC-BY-4.0 | 0.68 % | 101 MB | sherpa-onnx |
| WeSpeaker ResNet293-LM | CC-BY-4.0 | 0.45 % | 114 MB, 28 GMACs | sherpa-onnx |

- All these error rates are on whole sentences. None is published for clips of 1.5 s or less, or for a microphone across a room.
- CAM++ has no fix in sherpa's notes through 1.13.8. ERes2NetV2 has only a Chinese checkpoint.
- The bigger lever is probably not the model: enrol from Pebble's own microphone across the room, average over a whole turn, and keep several centroids per person (advice, not measured).
- A better model also makes the voice plan's fence stronger: it is what checks Pebble's own voice stays unlike anyone's.
- Switching means re-enrolling everyone (decision 4).

**Ladder:**
- **Pixel 6 Pro:** ResNet34-LM, or ReDimNet2-B2 if it wins.
- **Stronger phone:** TitaNet-L or ReDimNet2-B3, then ResNet293.
- **Measure:** ms to print a 3 s clip while the main model is busy; take the biggest model under about 60 ms, chosen once per phone.

**Verdict:** try ResNet34-LM first (a drop-in), then ReDimNet2-B2.

Sources: [TitaNet paper](https://ar5iv.labs.arxiv.org/html/2110.04410), [WeSpeaker results](https://arxiv.org/pdf/2210.17016), [WeSpeaker pretrained models and licence](https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md), [sherpa speaker models](https://huggingface.co/csukuangfj/speaker-embedding-models/tree/main), [ReDimNet2](https://github.com/PalabraAI/redimnet2), [sherpa-onnx releases](https://github.com/k2-fsa/sherpa-onnx/releases).

## Speech recognition

**Today.** NeMo FastConformer streaming, 114M parameters, 480 ms chunks (CC-BY-4.0).
- Our own harness: AMI meetings 25 % with headsets, 46 % across the table.
- Estimate: 0.4–0.8 of a big core while someone talks.

**Options** (AMI figures are the Open ASR leaderboard's headset scores, which use a different text normaliser from ours, so every option must be re-scored in our harness):
- **FUTO asr4all S / M / L** (FUTO weights licence; see decision 3).
  - Streaming CTC, 28 / 56 / 97M parameters; ONNX and ExecuTorch files.
  - AMI 13.1 / 11.2 / 9.9.
  - Published one-thread speed on a Pixel 4 at the default setting: 14.6 / 7.6 / 4.2 times faster than real time, so about 7 / 13 / 24 % of one core. That is 2–6 times cheaper than today, freeing cores for the main model.
  - It commits words more slowly: a latency floor of 0.76 / 0.92 / 1.08 s against today's 0.48 s chunks, finalised every 640 ms.
  - Not in sherpa: it needs Kotlin glue (its sound front end and a greedy CTC decoder).
- **NVIDIA Parakeet realtime EOU 120M** (NVIDIA Open Model License: commercial use allowed, a notice file required).
  - AMI 15.6 at 160 ms.
  - It emits an end-of-turn token a median 160 ms after speech ends (on synthetic speech), which could replace the 0.25 s silence rule.
  - About 1.5–2 times today's work (est.). Loading in sherpa is not confirmed.
- **NVIDIA Nemotron speech streaming 0.6B** (same licence). AMI 11.9 at 560 ms; sherpa has a 632 MB int8 package and a Qualcomm NPU path. 2–4 big cores on the Pixel (est.). Top rung only.
- **Moonshine v2 streaming** (MIT). Small: 123M, AMI 12.5. Its decoder slows as a transcript grows. Second in line.
- **Non-commercial options** found are weak. Allowing them buys nothing here.

**Ladder:**
- **Pixel 6 Pro:** asr4all-M if it beats today's model in our harness, otherwise today's model.
- **Stronger phone:** asr4all-L or Parakeet EOU, then Nemotron 0.6B on a Qualcomm NPU.
- **Measure:** real-time factor on a 10 s far-field clip while the main model decodes (step up at 0.35 or less of the core it gets); free memory at least the model plus 300 MB; an NPU transcript identical to the CPU's. Measure again after 10 minutes. Drop a rung after three utterances slower than 0.5, at thermal "severe", or on an error.

**Verdict:** try asr4all-M first (after decision 3), checking how long the last words take after speech ends.

Sources: [asr4all-M model card](https://huggingface.co/futo-org/asr4all-m), [asr4all licence](https://huggingface.co/futo-org/asr4all-s/raw/main/LICENSE), [Parakeet realtime EOU](https://huggingface.co/nvidia/parakeet_realtime_eou_120m-v1), [NVIDIA Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/), [Nemotron speech streaming](https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b), [sherpa NeMo models](https://k2-fsa.github.io/sherpa/onnx/nemo/index.html), [sherpa QNN](https://k2-fsa.github.io/sherpa/onnx/qnn/index.html), [Moonshine streaming](https://huggingface.co/UsefulSensors/moonshine-streaming-medium).

## Name spotting

**Today.** k2-fsa's zipformer keyword spotter (Apache-2.0, 3.3M). It found "Pebble" in 24 of 30 synthetic clips, never in the slowest male voice, and fired falsely once in 30 minutes of meetings.

**Options:**
- **livekit-wakeword** (Apache-2.0).
  - It trains a small model for one word from synthetic speech (Piper or VoxCPM voices), with noise, echo and pitch changes, on top of Google's speech-embedding feature models. It exports ONNX for ONNX Runtime.
  - Its authors' test ("hey livekit"): 0.08 false fires an hour against openWakeWord's 8.5, and 86 % found against 69 %.
  - Train "Pebble" with slow and low male voices included. Use it alongside today's spotter, which stays for the other phrases ("start listening") and for a build with another name.
  - A few % of a small core (est.).
  - The feature models' licences and the training voices' licences (some Piper voices are non-commercial, now allowed) are to check.
- **openWakeWord:** its ready-made models are CC-BY-NC-SA-4.0, not needed if we train our own.
- **microWakeWord:** no published accuracy.
- **Porcupine:** needs an online key, and its free keys stopped in June 2026. No.

**Ladder:** flat, since everything is cheap. On any phone, when words are on, a name hit can be checked against the recogniser's partial words.

**Verdict:** try and measure on the 30 clips and the 30 minutes of meetings.

Sources: [livekit-wakeword](https://github.com/livekit/livekit-wakeword), [openWakeWord](https://github.com/dscripka/openWakeWord), [microWakeWord](https://github.com/OHF-Voice/micro-wake-word), [sherpa keyword spotters](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html), [Porcupine free tier ending](https://community.home-assistant.io/t/fyi-picovoice-confirmed-free-tier-accesskeys-will-stop-working-after-june-30-2026/1012744).

## Voice activity

**Today.** Silero VAD. The pinned `silero_vad.onnx` (SHA-256 `9e2449e1…`) is k2-fsa's export of Silero v4.

**Options:**
- **Silero v6.2** (MIT). From Silero's own tests, v4 → v6:

  | | v4 | v6 |
  | --- | --- | --- |
  | AliMeeting, ROC-AUC | 0.89 | 0.96 |
  | AISHELL-4, ROC-AUC | 0.83 | 0.94 |
  | ESC-50 noise only, accuracy | 0.51 | 0.87 |
  | Private noise only, accuracy | 0.24 | 0.71 |

  So far fewer false starts from household noise, which also means fewer wasted recogniser runs. The cost is about the same. sherpa loads v5-shaped graphs; that v6 loads unchanged is not yet confirmed.
- **TEN VAD.** Apache-2.0 "with additional conditions": no use that competes with Agora, own applications only. Harmless for Pebble, but flag it. It claims to catch the end of speech sooner. Both rivals' tests rank it below Silero v6. Try it only as the end-of-speech and name-flush timer.
- **FireRedVAD** (Apache-2.0). The benchmarks contradict each other. Keep Silero.
- **Smart Turn v3.2** (BSD-2-Clause, 8 MB). It isn't a VAD: at each pause it judges whether the speaker has finished. 40–80 ms a pause on the phone (est.). Try it if the 0.25 s rule cuts people off.

**Verdict:** switch to Silero v6 after a load test and a replay of the existing recordings.

Sources: [Silero quality metrics](https://github.com/snakers4/silero-vad/wiki/Quality-Metrics), [Silero releases](https://github.com/snakers4/silero-vad/releases), [the v4 export's identity](https://huggingface.co/mobilebytesensei/betterflow-silero-vad), [TEN VAD licence](https://raw.githubusercontent.com/TEN-framework/ten-vad/main/LICENSE), [FireRedVAD](https://github.com/FireRedTeam/FireRedVAD), [Smart Turn](https://github.com/pipecat-ai/smart-turn).

## Sound events

**Today.** YAMNet (Apache-2.0), AudioSet mAP 0.306, looking at about 1 s of sound every 0.5 s.

**Options:**
- **CED-Tiny / CED-Mini** (weights Apache-2.0; the CED repo's code is GPL-3.0, which applies only if that code is reused).
  - AudioSet mAP 0.481 / 0.490, from 5.5M / 9.6M parameters.
  - sherpa-onnx already packages them as int8 (6.1 / 10.5 MB), for its offline audio-tagging API.
  - They were trained on 10 s clips; there are no published results for short windows, and no published compute.
  - Try a 2 s window every 0.5–1 s. Map the class names (CED has AudioSet's 527 classes, YAMNet 521), then re-tune the thresholds in the hearing table.
- **EfficientAT** (MIT). dymn04 reaches 0.450 at 0.12 GMACs and mn10 0.471. It needs our own export and sound front end. Try it if CED is slow.
- **PANNs CNN14** is heavier and worse; **BEATs** and **Dasheng** are too heavy to run all the time.

**Ladder:**
- **Pixel 6 Pro:** CED-Tiny, or EfficientAT dymn04.
- **Stronger phone:** CED-Mini, then CED-Small (22M, 0.496).
- **Measure:** ms per look while the main model is busy; keep it under about 3 % of a small core. The plain-code beep detector stays on every rung.

**Verdict:** try and measure on the alarm, glass, scream, baby and tap recordings.

Sources: [YAMNet](https://github.com/tensorflow/models/tree/master/research/audioset/yamnet), [CED-Tiny](https://huggingface.co/mispeech/ced-tiny), [CED code](https://github.com/RicherMans/CED), [sherpa CED-Mini](https://huggingface.co/k2-fsa/sherpa-onnx-ced-mini-audio-tagging-2024-04-19), [CED paper](https://arxiv.org/html/2308.11957), [EfficientAT](https://github.com/fschmid56/EfficientAT).

## Pebble's voice (text-to-speech and voice development)

**Today.** Android's own offline voice. The plan (section 6): Kokoro-82M through sherpa-onnx, with Pebble's voice blended from Kokoro's style vectors and then evolved slowly.

**The risk.** Published Kokoro speeds suggest it may be slower than real time on the Pixel 6 Pro while the main model runs. Real-time factor (RTF) is seconds of work per second of speech; above 1 means slower than real time:

| Device | Kokoro RTF |
| --- | --- |
| Raspberry Pi 4, sherpa fp32, 4 threads | 2.8–3.2 |
| Galaxy S23 Ultra, 2 threads | 1.8 (whole graph), 0.75–0.88 (short-turn graph) |
| Pixel 10 Pro, LiteRT | 0.93 |
| Pixel 6 Pro, 2 big threads under load (est.) | 1–2 |

A voice that is slower than real time stalls in the middle of sentences. Measure this before building the voice work on Kokoro.

| Model | Licence | Fits "its own voice, never a clone"? | Speed |
| --- | --- | --- | --- |
| Kokoro-82M | Apache-2.0; sherpa's version pulls in espeak-ng (GPL-3.0); the LiteRT port has an espeak-free front end | Yes: 256-number style vectors, blending is standard | see above |
| Kitten TTS nano / micro / mini (15 / 40 / 80M) | Apache-2.0; the LiteRT port is espeak-free | Yes: takes a style vector | nano RTF 0.19 on a Pi 5; quality likely below Kokoro (not measured) |
| Supertonic-3 (about 99M) | OpenRAIL-M weights (no impersonation without consent; disclose synthetic speech) | Partly: preset styles, blending unconfirmed | RTF 0.34 on an S23 Ultra, 832 MB peak |
| Pocket TTS (100M) | CC-BY-4.0, gated; forbids cloning without consent | Indirectly: its voice comes from a sample, which could be Pebble's own synthetic voice | About 6 times faster than real time on 2 M4 cores |
| Qwen3-TTS VoiceDesign 1.7B | Apache-2.0 | Yes: it designs a voice from a written description | Too slow for the phone; useful on the PC |
| Non-commercial ones (XTTS-v2, F5-TTS, Spark-TTS, OpenAudio S1-mini, IndexTTS2) | CPML, CC-BY-NC, CC-BY-NC-SA, bilibili licence | Mostly clone from a reference recording | All need a GPU; none is real time here |

Piper's engine is GPL-3.0 now, and its voices are real people's; Matcha is one real speaker. Both are poor fits for a voice of its own.

**Ladder:**
- **Pixel 6 Pro:** Kokoro if its under-load RTF is 0.6 or less; otherwise Kitten micro or mini with the same style-vector evolution. Whispers use the lightest rung.
- **Stronger phone:** Kokoro, on a GPU or NPU if it has one (an S26 GPU runs it at RTF 0.22).
- **Keeping one voice across rungs:** design the seed voice on the PC (Qwen3-TTS VoiceDesign can make one from a description, with no real person's recording), and train the floor model on lines spoken in Pebble's evolved voice.
- **Measure:** RTF and time to first sound on a fixed 6 s sentence while the main model decodes. Drop a rung above 0.7, or at thermal "moderate".

**Verdict:** keep the evolving-voice plan, but measure Kokoro first and don't tie the plan to one model (decision 5).

Sources: [sherpa Kokoro](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html), [Android TTS speeds (S23 Ultra)](https://github.com/soniqo/speech-android), [Kokoro on LiteRT](https://huggingface.co/litert-community/Kokoro-82M), [Kitten TTS](https://huggingface.co/KittenML/kitten-tts-nano-0.8), [Kitten on LiteRT](https://huggingface.co/litert-community/kitten-tts-nano-0.8), [Supertonic-3](https://huggingface.co/Supertone/supertonic-3), [Pocket TTS](https://huggingface.co/kyutai/pocket-tts), [Qwen3-TTS VoiceDesign](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign), [F5-TTS](https://huggingface.co/SWivid/F5-TTS), [Spark-TTS](https://huggingface.co/SparkAudio/Spark-TTS-0.5B), [OpenAudio S1-mini](https://huggingface.co/fishaudio/openaudio-s1-mini), [Matcha in sherpa](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/matcha.html).

## Main language model

**Today.** Gemma 4 E4B, Q4_K_M (4.98 GB), llama.cpp on the four fast cores, a 4,096-token window.
- **Licence:** Gemma 4 is Apache-2.0, not the old Gemma terms. `android/README.md` still says "Gemma terms of use".

**Reality check on speed.** Google's own CPU figures for E4B: a Galaxy S26 Ultra does 195 tokens/s reading the prompt and 18 tokens/s writing; a Raspberry Pi 5 does 51 and 3.
- Pixel 6 Pro estimate: 50–90 reading, 5–8 writing.
- So the sim's 8 words a second is likely too hopeful.
- A fresh 1,500-token prompt would take 17–30 s to read. Only a warm prompt cache makes the sim's 1.8 s to the first word possible: keep the fixed part of every prompt first and unchanged, so llama-server reuses it (`--cache-reuse`, `--slot-save-path`).

**Options (all Apache-2.0):**
- **Google's QAT checkpoint of the same model.** Trained to survive 4 bits.
  - Google's own Q4_0 file is 5.15 GB.
  - Unsloth's UD-Q4_K_XL made from the QAT weights is 4.22 GB, with mean KL divergence 0.0012 and 98.5 % top-1 agreement against full precision.
  - Q4_0 is the type llama.cpp repacks for the Pixel's dot-product cores, so compare both files for speed. **Switch.**
- **The E4B drafter** ("assistant", 4 layers, about 99 MB at Q8_0). The bundled llama.cpp already knows the `gemma4-assistant` architecture. Google claims up to 1.5 times faster writing on a phone CPU; one Galaxy report saw only 1–2 tokens/s more. Whether it works with the GBNF grammar is unconfirmed. **Try.**
- **Gemma 4 E2B** (QAT, 2.6–3.4 GB). About 2.4–2.9 times faster, but weaker (E2B against E4B):

  | MMLU-Pro | GPQA-Diamond | Tau2 |
  | --- | --- | --- |
  | 60.0 vs 69.4 | 43.4 vs 58.6 | 24.5 vs 42.2 |

  The step-down rung when hot or slow, not the default.
- **Qwen3.5-4B** (February 2026; built-in vision; Q4_K_M 2.74 GB, about half E4B's memory).
  - Liquid's comparison against E4B: tool calls (BFCLv3) 71.1 vs 57.3; Tau2-Retail 71.9 vs 42.1; IFEval about equal.
  - Against it: thinking is on by default, and must be turned off. Artificial Analysis reports a high hallucination rate. There is no chat or creative-writing comparison. Its DeltaNet layers' speed on phone CPUs is unknown.
  - **Try** it as the challenger on Pebble's own tests: persona, jokes, grammar-bound tool calls, decisions.
- **LFM2.5-8B-A1B** (LFM licence; 1.5B active). It always writes reasoning before answering and has no vision. Not for talking.
- **Non-commercial models** (Tiny Aya, Command R7B) are not better at this size.

**Ladder:**
- **Pixel 6 Pro:** E4B QAT, 4,096 tokens, warm prompt cache; E2B QAT as the automatic step-down; Qwen3.5-4B replaces E4B only if it wins the A/B. One experiment worth an evening: Google's LiteRT-LM on the Mali GPU. On an S26 Ultra its GPU reads E4B prompts at 1,293 tokens/s against 195 on the CPU, but Mali-G78 support is unconfirmed and it has no GBNF.
- **Stronger phone (16 GB):** E4B with a longer window (8–16k), the drafter and GPU or NPU prompt reading. Then Gemma 4 12B (Apache-2.0; MMLU-Pro 77.2, Tau2 69.0; about 6.7 GB at 4 bits) when it measures fast enough.
- **Measure:** reading and writing tokens/s and the time to the first token on a cached turn plus 60 new tokens, for 3 minutes with the ears, eyes and YAMNet running; free memory; thermal headroom. Take the highest rung with a cached first token in 1.5 s or less, writing at 6 tokens/s or more and 1.5 GB free. Drop to E2B at "moderate" or when writing falls below speaking speed.

**Verdict:** switch the file to QAT; try the drafter and Qwen3.5-4B.

Sources: [Gemma 4 E4B model card](https://huggingface.co/google/gemma-4-E4B-it), [Gemma 4 on Apache-2.0](https://opensource.googleblog.com/2026/03/gemma-4-expanding-the-gemmaverse-with-apache-20.html), [LiteRT-LM Gemma 4 speeds](https://developers.google.com/edge/litert-lm/models/gemma-4), [Google's QAT GGUF](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf), [Unsloth QAT notes](https://unsloth.ai/docs/models/gemma-4/qat), [Gemma MTP drafter](https://ai.google.dev/gemma/docs/mtp/mtp), [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B), [Artificial Analysis, Qwen3.5 small models](https://artificialanalysis.ai/es/articles/qwen3-5-small-models), [LFM2.5-8B-A1B (comparison table)](https://huggingface.co/LiquidAI/LFM2.5-8B-A1B), [Gemma 4 12B](https://huggingface.co/google/gemma-4-12b-it), [LiteRT-LM](https://developers.google.com/edge/litert-lm/overview).

## Small model

**Today.** LFM2.5-230M Q8_0 (247 MB) on two small cores.

**Option: LFM2.5-350M** (the same LFM Open License: Apache-2.0 with a US$10M revenue cap on commercial use; fine for Pebble). Against the 230M:

| | 230M | 350M |
| --- | --- | --- |
| IFEval | 71.7 | 77.0 |
| Multi-IF | 37.7 | 44.9 |
| Tau2-Telecom | 5.3 | 18.9 |

- Size: about 0.4 GB.
- Speed: 10–20 tokens/s on two A55s (est.).
- LFM2.5-1.2B is better again, but too slow for small cores.
- Qwen3.5-0.8B and Gemma 3 1B are worse.

**Ladder:**
- **Pixel 6 Pro:** 350M, with 230M as the fallback.
- **Stronger phone:** 1.2B on its middle cores.
- **Measure:** a 10-token choice after a cached 300-token prompt must finish within 0.5 s while the main model writes.

**Verdict:** try and measure.

Sources: [LFM2.5-350M](https://huggingface.co/LiquidAI/LFM2.5-350M), [LFM2.5-230M](https://huggingface.co/LiquidAI/LFM2.5-230M), [LFM2.5-1.2B](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct), [LFM Open License](https://www.liquid.ai/lfm-license).

## Picture understanding

**Today.** A 768 px JPEG goes to Gemma 4 E4B with its vision projector.
- `LlamaPlan` passes only `--mmproj`, so the picture budget is whatever the model file sets.

**The lever is the budget, not a new model.** Gemma 4 takes 70, 140, 280, 560 or 1,120 tokens a picture, and the bundled llama.cpp has `--image-max-tokens`.
- Estimates per picture on the Pixel: 1–2 s at 70 tokens, 2–3 s at 140, 4–6 s at 280.
- 768 px carries more detail than a 70–280-token budget uses, so shrink the picture to match.

**Options:**
- **Gemma 4's own vision:** one model in memory; MMMU-Pro 52.6. Keep.
- **LFM2.5-VL-450M** (LFM licence): beats SmolVLM2-500M on 12 of 13 listed tests. Worth it only if the main model ever goes text-only.
- **FastVLM** (Apple, research-only terms; no llama.cpp path found): no.
- **Moondream 3 preview** (BSL-1.1 with a use grant, 9B mixture of experts): too big for the floor.

**Ladder:**
- **Pixel 6 Pro:** 70 tokens for a glance, 140 by default, 280 only to read text.
- **Stronger phone:** 280–560 tokens with GPU prompt reading, or Gemma 4 12B's vision.
- **Measure:** seconds per picture at each budget under load; use the biggest that stays within about 2.5 s; drop to 70 when hot.

**Verdict:** keep Gemma 4's vision; set the budget.

Sources: [Gemma 4 E4B (budgets, MMMU-Pro)](https://huggingface.co/google/gemma-4-E4B-it), [llama.cpp server options (in the bundled source, `tools/server/README.md`)](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md), [LFM2.5-VL-450M](https://huggingface.co/LiquidAI/LFM2.5-VL-450M), [FastVLM licence](https://github.com/apple/ml-fastvlm/blob/main/LICENSE_MODEL), [Moondream 3 preview](https://huggingface.co/moondream/moondream3-preview).

## Object prints and place prints

**Today.** DINOv2-small (Apache-2.0, 21M), int8 ONNX, 384 numbers.
- Used for show and tell, Pebble's own things and the charger by sight (`look_for`, 3–4 s on the phone, estimated).
- Also for place prints, which are built but not used by anything yet.

**Option: DINOv3 ViT-S/16** (21M, the same size). Meta's paper (table 14):

| | DINOv2 ViT-S | DINOv3 ViT-S |
| --- | --- | --- |
| Oxford-Hard (finding the same place again) | 39.5 | 49.5 |
| NAVI (matching points on one object across views) | 53.4 | 56.3 |
| ImageNet-R | 54.0 | 60.4 |
| NYU depth error (lower is better) | 0.446 | 0.403 |

- Finding the same thing again is exactly what prints do (the same teapot, the same charger, the same room), and that score gains 10 points.
- Its 16-pixel patches mean fewer tokens for the same crop, so it is no slower. It takes any picture size natively.
- An ONNX export exists (onnx-community).
- ViT-S+ (29M) is a middle rung; ViT-B (86M, Oxford-Hard 58.5) a higher one.

**Licence:** Meta's DINOv3 Licence. Royalty-free and not limited to non-commercial, but:
- the download is gated;
- copies must carry the licence;
- no reverse engineering;
- banned uses: military, weapons, nuclear, espionage and trade-controlled uses.

**Switching cost:**
- Every stored print must be taken again: the charger's 8, and every known object.
- So each print needs a model tag, and the brain re-prints known things when it next sees them.
- The 0.75 match threshold must be checked again on the teapots and the rendered charger.

Place-recognition models (MegaLoc, SALAD, BoQ) are built on DINOv2-Base or larger, about 4 times the work. Not worth it while nothing uses place prints.

**Ladder:**
- **Pixel 6 Pro:** ViT-S/16, int8, 144 px crops.
- **Stronger phone:** ViT-S+, then ViT-B, with bigger crops in `look_for`. Chosen once per phone, like face prints.
- **Measure:** ms per print; `look_for` must stay under about 4 s.

**Verdict:** try and measure; switch if the teapot and charger checks hold or improve.

Sources: [DINOv3 ViT-S model card (gated)](https://huggingface.co/facebook/dinov3-vits16-pretrain-lvd1689m), [DINOv3 paper](https://arxiv.org/html/2508.10104), [DINOv3 Licence](https://github.com/facebookresearch/dinov3/blob/main/LICENSE.md), [ONNX export](https://mixpeek.com/model/onnx-community/dinov3-vits16-pretrain-lvd1689m-ONNX), [MegaLoc](https://arxiv.org/html/2502.17237v1), [SALAD](https://arxiv.org/pdf/2311.15937).

## Other places a licence held a choice back

- **Translation** (`plans/everyday-uses.md` 3f). NLLB-200 distilled 600M (CC-BY-NC-4.0) is now allowed, but it is about 1 GB at int8 (third-party estimate). Gemma 4 E4B is already loaded and multilingual, so try translating with it first. Opus-MT stays as the quick per-pair option; NLLB only for a pair both handle badly.
- **Watching 3D prints** (4b). Obico's failure detector is AGPL-3.0, the same licence as YOLOE, which Pebble already carries. It can be used instead of making one here (check its model files' own terms).
- **iFixit repair guides** (CC BY-NC-SA). Now usable on a personal Pebble; anything made from them stays share-alike.

## Licence notes for NOTES.md ("Licences of the parts")

When any change above is adopted, add it to the list. Not done here, as this survey changes no repo file but this report.

- **Non-commercial:**
  - MobileCLIP2, for the word lists (research only);
  - InsightFace face models (research only);
  - V2 Base, if used for still scans (CC-BY-NC-4.0);
  - EdgeFace, if used (CC-BY-NC-SA-4.0, share-alike).
- **Field-of-use or extra conditions:**
  - FUTO asr4all (surveillance, covert interception, profiling bans);
  - DINOv3 Licence (gated, banned uses);
  - TEN VAD (Agora conditions), if used;
  - Supertonic (OpenRAIL-M), if used;
  - LFM Open License (US$10M cap);
  - NVIDIA Open Model License (notice file), if Parakeet or Nemotron is used.
- **Copyleft:**
  - espeak-ng (GPL-3.0), inside sherpa's Kokoro;
  - CED's code (GPL-3.0), only if reused, not its weights.
- **Credit:**
  - WeSpeaker and VoxCeleb (CC-BY-4.0);
  - Pocket TTS (CC-BY-4.0), if used;
  - NVIDIA NeMo, as today.
- **Fix:** `android/README.md` says Gemma 4 is under the Gemma terms of use; it is Apache-2.0.
