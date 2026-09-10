import copy
import unittest

from frameweave.workflows import capabilities, catalog, compile_workflow, validate_prompt


def schema(required, output, optional=None, output_node=False):
    return {"input": {"required": required, "optional": optional or {}},
            "output": output, "output_node": output_node}


def fixture():
    integer = ["INT", {"min": 0, "max": 2**64 - 1}]
    number = ["FLOAT", {"min": 0, "max": 100}]
    text = ["STRING"]
    model = ["MODEL"]
    latent = ["LATENT"]
    image = ["IMAGE"]
    conditioning = ["CONDITIONING"]
    dims = {"width": integer, "height": integer}
    c = {
        "CheckpointLoaderSimple": schema({"ckpt_name": [["checkpoints/studio_xl.safetensors"]]}, ["MODEL", "CLIP", "VAE"]),
        "UNETLoader": schema({"unet_name": [["diffusion_models/minimax_h3_fl2va_int8.safetensors", "diffusion_models/minimax_h3_ref2va_int8.safetensors", "diffusion_models/krea2_turbo_fp8.safetensors"]], "weight_dtype": [["default"]]}, ["MODEL"]),
        "CLIPLoader": schema({"clip_name": [["text_encoders/qwen3vl_32b_minimax_h3.safetensors", "text_encoders/qwen3vl_4b.safetensors"]], "type": [["minimax", "krea2"]]}, ["CLIP"]),
        "VAELoader": schema({"vae_name": [["vae/minimax_h3_video_vae.safetensors", "vae/minimax_h3_audio_vae.safetensors", "vae/qwen_image_vae.safetensors"]]}, ["VAE"]),
        "CLIPTextEncode": schema({"clip": ["CLIP"], "text": text}, ["CONDITIONING"]),
        "ConditioningZeroOut": schema({"conditioning": conditioning}, ["CONDITIONING"]),
        "KSampler": schema({"model": model, "seed": integer, "steps": ["INT", {"min": 1, "max": 1000}], "cfg": number, "sampler_name": [["euler", "heun"]], "scheduler": [["simple", "karras"]], "positive": conditioning, "negative": conditioning, "latent_image": latent, "denoise": ["FLOAT", {"min": 0, "max": 1}]}, ["LATENT"]),
        "EmptyLatentImage": schema(dict(dims, batch_size=integer), ["LATENT"]),
        "EmptySD3LatentImage": schema(dict(dims, batch_size=integer), ["LATENT"]),
        "VAEEncode": schema({"pixels": image, "vae": ["VAE"]}, ["LATENT"]),
        "VAEDecode": schema({"samples": latent, "vae": ["VAE"]}, ["IMAGE"]),
        "VAEDecodeAudio": schema({"samples": latent, "vae": ["VAE"]}, ["AUDIO"]),
        "SaveImage": schema({"images": image, "filename_prefix": text}, [], output_node=True),
        "LoadImage": schema({"image": [["first.png", "last.png", "style.png"]]}, ["IMAGE", "MASK"]),
        "ImageScale": schema(dict(dims, image=image, upscale_method=[["lanczos"]], crop=[["center"]]), ["IMAGE"]),
        "MiniMaxH3ImageToVideo": schema(dict(dims, clip=["CLIP"], vae=["VAE"], prompt=text, length=integer), ["CONDITIONING", "LATENT"], {"first_frame": image, "last_frame": image}),
        "MiniMaxH3ReferenceToVideo": schema(dict(dims, clip=["CLIP"], vae=["VAE"], audio_vae=["VAE"], prompt=text, length=integer, ref_image_size=["COMBO", {"options": ["match", "max"]}]), ["CONDITIONING", "LATENT"], {"ref_images": ["COMFY_AUTOGROW_V3", {"template": {"input": {"required": {"ref_image": image}}, "prefix": "ref_image_", "min": 0, "max": 9}}]}),
        "MiniMaxH3SigmaShift": schema({"model": model, "shift_video": number, "shift_audio": number}, ["MODEL"]),
        "LTXVSeparateAVLatent": schema({"av_latent": latent}, ["LATENT", "LATENT"]),
        "CreateVideo": schema({"images": image, "fps": number}, ["VIDEO"], {"audio": ["AUDIO"]}),
        "SaveVideo": schema({"video": ["VIDEO"], "filename_prefix": text, "format": ["COMBO", {"options": ["mp4", "auto"]}], "codec": ["COMFY_DYNAMICCOMBO_V3", {"options": [{"key": "auto", "inputs": {}}, {"key": "h264", "inputs": {"optional": {"crf": number}}}]}]}, ["VIDEO"], output_node=True),
        "Krea2OstrisEditModelPatch": schema({"model": model}, ["MODEL"]),
        "TextEncodeKrea2OstrisEdit": schema({"clip": ["CLIP"], "prompt": text}, ["CONDITIONING"], {"vae": ["VAE"], "image1": image, "image2": image, "image3": image}),
        "LoraLoaderModelOnly": schema({"model": model, "lora_name": [["loras/turbo.safetensors"]], "strength_model": number}, ["MODEL"]),
        "LoraLoaderBypassModelOnly": schema({"model": model, "lora_name": [["loras/turbo.safetensors"]], "strength_model": number}, ["MODEL"]),
        "LoraLoader": schema({"model": model, "clip": ["CLIP"], "lora_name": [["loras/turbo.safetensors"]], "strength_model": number, "strength_clip": number}, ["MODEL", "CLIP"]),
        "MiniMaxH3DualClockSamplerT8": schema({"model": model, "av_latent": latent, "steps": integer, "shift_video": number, "shift_audio": number}, ["MODEL", "SAMPLER", "SIGMAS"], {"sampler_name": ["COMBO", {"options": ["dual_clock_euler"]}], "scheduler": ["COMBO", {"options": ["native_flow", "simple"]}]}),
        "RandomNoise": schema({"noise_seed": integer}, ["NOISE"]),
        "BasicGuider": schema({"model": model, "conditioning": conditioning}, ["GUIDER"]),
        "SamplerCustomAdvanced": schema({"noise": ["NOISE"], "guider": ["GUIDER"], "sampler": ["SAMPLER"], "sigmas": ["SIGMAS"], "latent_image": latent}, ["LATENT", "LATENT"]),
    }
    return c


def nodes(result, class_type):
    return [n["inputs"] for n in result["prompt"].values() if n["class_type"] == class_type]


class WorkflowTests(unittest.TestCase):
    def test_shared_model_root_excludes_non_generation_model_roles(self):
        info = {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [[
            "Library/SDXL/Checkpoints/base.safetensors", "Library/Embeddings/SDXL/negative.safetensors",
            "Library/ControlNet/model.safetensors", "Library/clip_vision/model.safetensors"
        ]]}}}}
        self.assertEqual(catalog(info)["checkpoint"], ["Library/SDXL/Checkpoints/base.safetensors"])

    def setUp(self):
        self.info = fixture()

    def compile(self, kind="h3_t2v", **kwargs):
        return compile_workflow(dict(kind=kind, positive="A blue paper bird on a quiet desk.", **kwargs), self.info)

    def test_h3_native_compiler_preserves_audio_and_frame_grid(self):
        result = self.compile(seconds=5)
        self.assertEqual(result["summary"]["frames"], 124)
        self.assertAlmostEqual(result["summary"]["seconds"], 124 / 24)
        self.assertEqual(nodes(result, "CLIPLoader")[0]["type"], "minimax")
        self.assertEqual(nodes(result, "CreateVideo")[0]["fps"], 24)
        self.assertIn("audio", nodes(result, "CreateVideo")[0])
        self.assertEqual(nodes(result, "KSampler")[0]["steps"], 20)
        self.assertEqual(len(nodes(result, "MiniMaxH3SigmaShift")), 1)

    def test_h3_first_last_and_dynamic_references(self):
        result = self.compile("h3_i2v", references=["first.png", "last.png"])
        self.assertIn("first_frame", nodes(result, "MiniMaxH3ImageToVideo")[0])
        self.assertIn("last_frame", nodes(result, "MiniMaxH3ImageToVideo")[0])
        result = self.compile("h3_ref", references=["first.png", "style.png"])
        ref = nodes(result, "MiniMaxH3ReferenceToVideo")[0]
        self.assertIn("ref_images.ref_image_0", ref)
        self.assertIn("ref_images.ref_image_1", ref)
        self.assertIn("ref2va", result["summary"]["models"]["dit"])

    def test_dynamic_input_prefix_is_discovered(self):
        spec = self.info["MiniMaxH3ReferenceToVideo"]["input"]["optional"]["ref_images"][1]
        spec["template"]["prefix"] = "picture_"
        result = self.compile("h3_ref", references=["first.png"])
        self.assertIn("ref_images.picture_0", nodes(result, "MiniMaxH3ReferenceToVideo")[0])

    def test_dual_clock_has_no_duplicate_sigma_shift(self):
        result = self.compile(sampler="dual_clock_euler", lora="loras/turbo.safetensors", steps=4)
        self.assertFalse(nodes(result, "MiniMaxH3SigmaShift"))
        self.assertEqual(len(nodes(result, "LoraLoaderBypassModelOnly")), 1)
        self.assertEqual(nodes(result, "MiniMaxH3DualClockSamplerT8")[0]["scheduler"], "native_flow")
        with self.assertRaises(ValueError):
            self.compile(sampler="dual_clock_euler", cfg=3)

    def test_krea_text_and_image_edit(self):
        result = self.compile("krea")
        self.assertEqual(nodes(result, "CLIPLoader")[0]["type"], "krea2")
        self.assertEqual(nodes(result, "KSampler")[0]["steps"], 8)
        self.assertEqual(nodes(result, "KSampler")[0]["sampler_name"], "euler")
        self.assertEqual(nodes(result, "KSampler")[0]["scheduler"], "simple")
        self.assertEqual(len(nodes(result, "EmptySD3LatentImage")), 1)
        result = self.compile("krea", references=["first.png", "style.png"], denoise=0.7)
        self.assertIn("image2", nodes(result, "TextEncodeKrea2OstrisEdit")[0])
        self.assertEqual(len(nodes(result, "Krea2OstrisEditModelPatch")), 1)
        self.assertEqual(len(nodes(result, "VAEEncode")), 1)
        self.assertEqual(nodes(result, "ImageScale")[0]["width"], 1024)

    def test_sdxl_checkpoint_and_image_to_image(self):
        result = self.compile("sdxl", references=["first.png"], denoise=0.6)
        self.assertEqual(len(nodes(result, "CheckpointLoaderSimple")), 1)
        self.assertEqual(nodes(result, "KSampler")[0]["denoise"], 0.6)
        self.assertEqual(len(nodes(result, "SaveImage")), 1)

    def test_missing_plugin_fails_before_submission(self):
        del self.info["TextEncodeKrea2OstrisEdit"]
        with self.assertRaisesRegex(ValueError, "TextEncodeKrea2OstrisEdit"):
            self.compile("krea", references=["first.png"])

    def test_model_catalog_filters_mixed_root(self):
        all_names = ["Library/MiniMaxH3/Diffusion/minimax_h3_fl2va.safetensors",
                     "Library/MiniMaxH3/TextEncoder/qwen3vl_32b_minimax_h3.safetensors",
                     "Library/MiniMaxH3/VAE/minimax_h3_video_vae.safetensors",
                     "Library/MiniMaxH3/VAE/minimax_h3_audio_vae.safetensors",
                     "Library/MiniMaxH3/LoRA/Acceleration/turbo.safetensors"]
        for node, field in [("UNETLoader", "unet_name"), ("CLIPLoader", "clip_name"), ("VAELoader", "vae_name"), ("LoraLoaderModelOnly", "lora_name")]:
            self.info[node]["input"]["required"][field] = [all_names]
        result = catalog(self.info)
        self.assertEqual(result["dit"], all_names[:1])
        self.assertEqual(result["text_encoder"], all_names[1:2])
        self.assertEqual(result["vae"], all_names[2:3])
        self.assertEqual(result["audio_vae"], all_names[3:4])
        self.assertEqual(result["lora"], all_names[4:])

    def test_capabilities_follow_node_and_clip_support(self):
        self.assertEqual(capabilities(self.info), {"h3": True, "sdxl": True, "krea": True})
        del self.info["MiniMaxH3ImageToVideo"]
        self.assertFalse(capabilities(self.info)["h3"])
        self.info["CLIPLoader"]["input"]["required"]["type"] = [["minimax"]]
        self.assertFalse(capabilities(self.info)["krea"])

    def test_h3_rejects_invalid_modes_and_dimensions(self):
        for request in [dict(width=735), dict(fps=30), dict(width=1920, height=1920),
                        dict(seed=-1), dict(steps=True), dict(references=["../first.png"]),
                        dict(kind="h3_i2v"), dict(kind="h3_ref", references=[]),
                        dict(sampler="fake"), dict(denoise=0.5)]:
            with self.subTest(request=request), self.assertRaises(ValueError):
                compile_workflow(dict(positive="Test", **request), self.info)

    def test_validation_detects_missing_inputs_types_slots_enums_and_cycles(self):
        base = self.compile("sdxl")["prompt"]
        sampler_id = next(k for k, v in base.items() if v["class_type"] == "KSampler")
        cases = [lambda p: p[sampler_id]["inputs"].pop("model"),
                 lambda p: p[sampler_id]["inputs"].update(model=["1", 1]),
                 lambda p: p[sampler_id]["inputs"].update(model=["1", 99]),
                 lambda p: p[sampler_id]["inputs"].update(model=["missing", 0]),
                 lambda p: p[sampler_id]["inputs"].update(sampler_name="unknown"),
                 lambda p: p[sampler_id]["inputs"].update(steps=True),
                 lambda p: p[sampler_id]["inputs"].update(cfg=float("nan")),
                 lambda p: p[sampler_id]["inputs"].update(denoise=2),
                 lambda p: p[sampler_id]["inputs"].update(unused=True),
                 lambda p: p[sampler_id]["inputs"].update(latent_image=[sampler_id, 0])]
        for change in cases:
            prompt = copy.deepcopy(base)
            change(prompt)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_prompt(prompt, self.info)

    def test_api_is_copied_and_validated(self):
        prompt = self.compile("sdxl")["prompt"]
        result = compile_workflow({"kind": "api", "prompt": prompt}, self.info)
        result["prompt"]["1"]["inputs"]["ckpt_name"] = "changed"
        self.assertNotEqual(result["prompt"], prompt)
        with self.assertRaises(ValueError):
            compile_workflow({"kind": "api", "prompt": {}}, self.info)

    def test_api_wrapper_and_malformed_values(self):
        prompt = self.compile("sdxl")["prompt"]
        result = compile_workflow({"kind": "api", "workflow": {"prompt": prompt}}, self.info)
        self.assertEqual(result["prompt"], prompt)
        for invalid in [None, [], {"prompt": 3}, {"1": {"inputs": {}, "class_type": []}}]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                compile_workflow({"kind": "api", "prompt": invalid}, self.info)
        with self.assertRaises(ValueError):
            self.compile(seed=10**1000)

    def test_dynamic_combo_only_accepts_active_branch_fields(self):
        result = self.compile()
        graph = result["prompt"]
        save = next(n for n in graph.values() if n["class_type"] == "SaveVideo")
        save["inputs"]["codec.crf"] = 18.0
        validate_prompt(graph, self.info)
        save["inputs"]["codec"] = "auto"
        with self.assertRaisesRegex(ValueError, "codec.crf"):
            validate_prompt(graph, self.info)

    def test_references_cannot_escape_backend_input_directory(self):
        for name in ["C:/private.png", "../input.png", "/absolute.png", "a/../../x.png", "bad\x00.png"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.compile("h3_i2v", references=[name])

    def test_h3_memory_defaults_and_explicit_pruned_lora(self):
        pruned = "diffusion_models/minimax_h3_fl2va_pruned_int8.safetensors"
        nvfp4 = "text_encoders/qwen3vl_32b_minimax_h3_nvfp4.safetensors"
        self.info["UNETLoader"]["input"]["required"]["unet_name"][0].append(pruned)
        self.info["CLIPLoader"]["input"]["required"]["clip_name"][0].append(nvfp4)
        result = self.compile()
        self.assertEqual(result["summary"]["models"]["dit"], pruned)
        self.assertEqual(result["summary"]["models"]["text_encoder"], nvfp4)
        result = self.compile(models={"dit": pruned}, lora="loras/turbo.safetensors")
        self.assertTrue(any("pruned" in text for text in result["summary"]["warnings"]))

    def test_zero_cfg_warns_that_positive_is_not_guidance(self):
        result = self.compile("krea", cfg=0)
        self.assertTrue(any("CFG=0" in text for text in result["summary"]["warnings"]))

    def test_explicit_known_incompatible_model_families_are_rejected(self):
        self.info["UNETLoader"]["input"]["required"]["unet_name"][0].append("diffusion_models/flux1-dev.safetensors")
        self.info["VAELoader"]["input"]["required"]["vae_name"][0].append("vae/ae.safetensors")
        self.info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0].append("checkpoints/v1-5-pruned.safetensors")
        cases = [
            ("h3_t2v", {"dit": "diffusion_models/krea2_turbo_fp8.safetensors"}),
            ("h3_t2v", {"text_encoder": "text_encoders/qwen3vl_4b.safetensors"}),
            ("h3_t2v", {"vae": "vae/qwen_image_vae.safetensors"}),
            ("h3_t2v", {"dit": "diffusion_models/minimax_h3_ref2va_int8.safetensors"}),
            ("h3_ref", {"dit": "diffusion_models/minimax_h3_fl2va_int8.safetensors"}),
            ("krea", {"dit": "diffusion_models/flux1-dev.safetensors"}),
            ("krea", {"vae": "vae/ae.safetensors"}),
            ("krea", {"text_encoder": "text_encoders/qwen3vl_32b_minimax_h3.safetensors"}),
            ("sdxl", {"checkpoint": "checkpoints/v1-5-pruned.safetensors"}),
        ]
        for kind, models in cases:
            with self.subTest(kind=kind, models=models), self.assertRaises(ValueError):
                self.compile(kind, models=models, references=["first.png"] if kind == "h3_ref" else [])

    def test_explicit_unknown_custom_names_are_not_rejected_as_wrong_family(self):
        model_names = {"dit": "custom-weights.safetensors", "text_encoder": "my-custom-encoder.safetensors", "vae": "custom-decoder.safetensors"}
        for node, field, role in [("UNETLoader", "unet_name", "dit"), ("CLIPLoader", "clip_name", "text_encoder"), ("VAELoader", "vae_name", "vae")]:
            self.info[node]["input"]["required"][field][0].append(model_names[role])
        result = self.compile("krea", models=model_names)
        self.assertEqual(result["summary"]["models"], model_names)

    def test_cloud_nodes_are_rejected_even_in_api_mode(self):
        self.info["CloudImage"] = schema({"prompt": ["STRING"]}, ["IMAGE"])
        self.info["CloudImage"]["api_node"] = True
        prompt = {"1": {"class_type": "CloudImage", "inputs": {"prompt": "A blue bird"}}}
        with self.assertRaisesRegex(ValueError, "云端"):
            compile_workflow({"kind": "api", "prompt": prompt}, self.info)

    def test_graph_node_json_and_dependency_depth_are_bounded(self):
        info = {"Start": schema({}, ["LATENT"]), "Next": schema({"value": ["LATENT"]}, ["LATENT"])}
        graph = {"0": {"class_type": "Start", "inputs": {}}}
        for i in range(1, 256):
            graph[str(i)] = {"class_type": "Next", "inputs": {"value": [str(i - 1), 0]}}
        validate_prompt(graph, info)
        graph["256"] = {"class_type": "Next", "inputs": {"value": ["255", 0]}}
        with self.assertRaisesRegex(ValueError, "256"):
            validate_prompt(graph, info)
        graph = {str(i): {"class_type": "Start", "inputs": {}} for i in range(1001)}
        with self.assertRaisesRegex(ValueError, "1000"):
            validate_prompt(graph, info)
        nested = {}
        for _ in range(65):
            nested = {"data": nested}
        graph = {"1": {"class_type": "Start", "inputs": {}, "_meta": nested}}
        with self.assertRaisesRegex(ValueError, "64"):
            validate_prompt(graph, info)

    def test_first_last_roles_take_precedence_over_array_order(self):
        result = self.compile("h3_i2v", references=["last.png", "first.png"], reference_roles=["end", "start"])
        condition = nodes(result, "MiniMaxH3ImageToVideo")[0]
        first_loader = result["prompt"][condition["first_frame"][0]]
        last_loader = result["prompt"][condition["last_frame"][0]]
        self.assertEqual(first_loader["inputs"]["image"], "first.png")
        self.assertEqual(last_loader["inputs"]["image"], "last.png")
        result = self.compile("h3_i2v", references=["last.png"], reference_roles=["last_frame"])
        self.assertNotIn("first_frame", nodes(result, "MiniMaxH3ImageToVideo")[0])
        self.assertIn("last_frame", nodes(result, "MiniMaxH3ImageToVideo")[0])
        result = self.compile("h3_i2v", references=["first.png", "last.png"], reference_roles=["reference", "end"])
        self.assertEqual(result["summary"]["reference_roles"], ["start", "end"])
        result = self.compile("h3_i2v", references=["first.png", "last.png"], reference_roles=["reference", "reference"])
        self.assertEqual(result["summary"]["reference_roles"], ["start", "end"])
        for roles in [["start", "start"], ["start"], ["unknown", "end"]]:
            with self.subTest(roles=roles), self.assertRaises(ValueError):
                self.compile("h3_i2v", references=["first.png", "last.png"], reference_roles=roles)

    def test_large_user_controls_warn_and_report_exact_supported_duration(self):
        result = self.compile(seconds=150, steps=1000)
        self.assertEqual(result["summary"]["steps"], 1000)
        self.assertEqual(result["summary"]["frames"], 3592)
        self.assertEqual(result["summary"]["requested_seconds"], 150)
        self.assertAlmostEqual(result["summary"]["seconds"], 3592 / 24)
        self.assertTrue(any("上限" in text for text in result["summary"]["warnings"]))
        self.assertTrue(any("较高步数" in text for text in result["summary"]["warnings"]))


if __name__ == "__main__":
    unittest.main()
