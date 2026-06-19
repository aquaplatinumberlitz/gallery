"""
Purpose:
Unit-test the metadata parsers that recognize A1111, ComfyUI, SwarmUI,
NovelAI, and EasyDiffusion metadata from image text chunks, and verify the
tool-detection dispatch in _api_metadata_from_sources.

Guarantees:
* parse_a1111_parameters extracts prompt/negative/Steps/Sampler/CFG/Seed/Model
  for well-formed parameter text and degrades gracefully for empty, short, or
  malformed input.
* parse_comfy normalises dict-style and list-style prompt JSON, resolves linked
  node inputs, and returns {} for invalid JSON.
* SwarmUI, NovelAI, and EasyDiffusion detectors only activate for their own
  JSON shapes and reject unrelated or invalid payloads.
* _api_metadata_from_sources chooses the highest-priority tool and falls back
  to .txt sidecars and generic text keys before returning Unknown.
* extract_loras and helper parsers (parse_int, parse_float) handle edge cases.

Run when:
* changing any parser in metadata_extract.py
* adding a new AI tool format
* refactoring metadata source dispatch
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.metadata_extract import (
    _api_metadata_from_sources,
    _parse_easydiffusion_metadata,
    _parse_novelai_metadata,
    _parse_swarm_metadata,
    extract_loras,
    parse_a1111_parameters,
    parse_comfy,
    parse_float,
    parse_int,
)

# ---------------------------------------------------------------------------
# parse_a1111_parameters
# ---------------------------------------------------------------------------


class TestParseA1111Parameters:
    def test_full_parameters(self):
        text = (
            "masterpiece, 1girl, sunset\n"
            "Negative prompt: low quality, blurry\n"
            "Steps: 30, Sampler: Euler a, CFG scale: 7.5, Seed: 12345, Size: 512x768, Model: myModel_v1"
        )
        result = parse_a1111_parameters(text)
        assert result["prompt"] == "masterpiece, 1girl, sunset"
        assert result["negative_prompt"] == "low quality, blurry"
        assert result["steps"] == 30
        assert result["sampler"] == "Euler a"
        assert result["cfg_scale"] == 7.5
        assert result["seed"] == "12345"
        assert result["model"] == "myModel_v1"

    def test_prompt_only(self):
        text = "a beautiful landscape"
        result = parse_a1111_parameters(text)
        assert result["prompt"] == "a beautiful landscape"
        assert result["negative_prompt"] == ""
        assert result["steps"] is None
        assert result["sampler"] == ""
        assert result["cfg_scale"] is None
        assert result["seed"] == ""
        assert result["model"] == ""

    def test_prompt_and_neg_no_params(self):
        text = "hills and valleys\nNegative prompt: watermarks"
        result = parse_a1111_parameters(text)
        assert result["prompt"] == "hills and valleys"
        assert result["negative_prompt"] == "watermarks"

    def test_empty_string(self):
        result = parse_a1111_parameters("")
        assert result["prompt"] == ""
        assert result["negative_prompt"] == ""
        assert result["steps"] is None

    def test_malformed_numeric_values(self):
        text = "test prompt\nNegative prompt: bad\nSteps: abc, Sampler: Euler, CFG scale: xyz, Seed: nan, Model: model"
        result = parse_a1111_parameters(text)
        assert result["prompt"] == "test prompt"
        assert result["steps"] is None
        assert result["cfg_scale"] is None
        assert result["seed"] == "nan"
        assert result["model"] == "model"

    def test_seed_with_spaces(self):
        text = "prompt\nSteps: 20, Sampler: DPM, CFG scale: 5.0, Seed: 4294967295, Model: sdxl"
        result = parse_a1111_parameters(text)
        assert result["seed"] == "4294967295"

    def test_prompt_with_neg_but_no_settings_markers(self):
        text = "beautiful cat\nNegative prompt: ugly, deformed"
        result = parse_a1111_parameters(text)
        assert result["prompt"] == "beautiful cat"
        assert result["negative_prompt"] == "ugly, deformed"
        assert result["steps"] is None


# ---------------------------------------------------------------------------
# parse_comfy
# ---------------------------------------------------------------------------


class TestParseComfy:
    def test_dict_style_prompt_json(self):
        data = {
            "1": {
                "inputs": {"text": "masterpiece, 1girl"},
                "class_type": "CLIPTextEncode",
            },
            "2": {
                "inputs": {"text": "ugly, bad"},
                "class_type": "CLIPTextEncode",
            },
            "3": {
                "inputs": {
                    "seed": 12345,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "model": ["4", 0],
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                },
                "class_type": "KSampler",
            },
            "4": {
                "inputs": {"ckpt_name": "sd_xl_base.safetensors"},
                "class_type": "CheckpointLoaderSimple",
            },
        }
        result = parse_comfy(json.dumps(data), None)
        assert result["tool"] == "ComfyUI"
        assert "masterpiece, 1girl" in result["prompt"]
        assert "ugly, bad" in result["negative_prompt"]
        assert "12345" in result["params"]["Seed"]
        assert "20" in result["params"]["Steps"]
        assert "7.0" in result["params"]["CFG"]
        assert "euler" in result["params"]["Sampler"]
        assert "sd_xl_base.safetensors" in result["params"]["Model"]

    def test_workflow_fallback_when_prompt_invalid(self):
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CLIPTextEncode",
                    "inputs": {"text": "from workflow"},
                },
                {
                    "id": 2,
                    "type": "KSampler",
                    "inputs": {"seed": 42, "steps": 10, "cfg": 8.0, "sampler_name": "dpm"},
                },
            ]
        }
        result = parse_comfy("not json", json.dumps(workflow))
        assert result["tool"] == "ComfyUI"
        assert result["prompt"] == "from workflow"
        assert result["params"]["Seed"] == "42"

    def test_list_style_nodes(self):
        data = {
            "nodes": [
                {"id": 1, "type": "CLIPTextEncode", "inputs": {"text": "test prompt"}},
                {"id": 2, "type": "KSampler", "inputs": {"seed": 99, "steps": 30, "cfg": 6.0, "sampler": "euler_a"}},
            ]
        }
        result = parse_comfy(json.dumps(data), None)
        assert result["tool"] == "ComfyUI"
        assert result["prompt"] == "test prompt"
        assert result["params"]["Seed"] == "99"

    def test_linked_input_resolution_seed_steps_cfg_from_referenced_node(self):
        data = {
            "nodes": [
                {"id": 10, "type": "PrimitiveNode", "inputs": {"value": 888}},
                {"id": 20, "type": "PrimitiveNode", "inputs": {"value": 25}},
                {"id": 30, "type": "PrimitiveNode", "inputs": {"value": 9.5}},
                {
                    "id": 1,
                    "type": "KSampler",
                    "inputs": {
                        "seed": [10, 0],
                        "steps": [20, 0],
                        "cfg": [30, 0],
                        "sampler_name": "dpmpp",
                    },
                },
            ]
        }
        result = parse_comfy(json.dumps(data), None)
        assert result["params"]["Seed"] == "888"
        assert result["params"]["Steps"] == "25"
        assert result["params"]["CFG"] == "9.5"

    def test_no_circular_infinite_loop_in_resolve(self):
        data = {
            "nodes": [
                {"id": 1, "type": "KSampler", "inputs": {"seed": [1, 0], "steps": [1, 1], "cfg": [1, 2]}},
            ]
        }
        result = parse_comfy(json.dumps(data), None)
        assert "Seed" not in result["params"]
        assert "CFG" not in result["params"]

    def test_invalid_json_returns_empty_dict(self):
        result = parse_comfy("not valid json at all", None)
        assert result == {}

    def test_dict_is_not_a_recognised_shape(self):
        result = parse_comfy("[]", None)
        assert result == {}

    def test_vaeloader_and_upscale_and_controlnet_and_lora_and_clipsetlastlayer(self):
        data = {
            "nodes": [
                {"id": 1, "type": "VAELoader", "inputs": {"vae_name": "vae-ft-mse.safetensors"}},
                {"id": 2, "type": "UpscaleModelLoader", "inputs": {"model_name": "4x-UltraSharp.pth"}},
                {"id": 3, "type": "ControlNetLoader", "inputs": {"control_net_name": "canny.safetensors"}},
                {
                    "id": 4,
                    "type": "LoraLoader",
                    "inputs": {"lora_name": "detailer.safetensors", "strength_model": 0.75},
                },
                {"id": 5, "type": "CLIPSetLastLayer", "inputs": {"stop_at_clip_layer": -2}},
            ]
        }
        result = parse_comfy(json.dumps(data), None)
        assert result["params"]["VAE"] == "vae-ft-mse.safetensors"
        assert result["params"]["UpscaleModel"] == "4x-UltraSharp.pth"
        assert result["params"]["ControlNet"] == "canny.safetensors"
        assert "detailer:0.75" in result["params"]["Lora"]
        assert result["params"]["clip_skip"] == "-2"

    def test_lora_in_prompt_text_extracted(self):
        data = {
            "nodes": [
                {"id": 1, "type": "CLIPTextEncode", "inputs": {"text": "1girl <lora:detail:0.8>"}},
                {"id": 2, "type": "KSampler", "inputs": {"seed": 1, "steps": 1, "cfg": 1.0, "sampler_name": "euler"}},
            ]
        }
        result = parse_comfy(json.dumps(data), None)
        assert "detail:0.8" in result["params"]["Lora"]

    def test_lora_name_strips_safetensors(self):
        data = {
            "nodes": [
                {"id": 1, "type": "LoraLoader", "inputs": {"lora_name": "my_lora.safetensors", "strength_model": 0.5}},
            ]
        }
        result = parse_comfy(json.dumps(data), None)
        assert "my_lora:0.5" in result["params"]["Lora"]

    def test_ksampler_advanced_recognised(self):
        data = {
            "nodes": [
                {"id": 1, "type": "KSamplerAdvanced", "inputs": {"seed": 7, "steps": 12, "cfg_scale": 4.0}},
            ]
        }
        result = parse_comfy(json.dumps(data), None)
        assert result["params"]["Seed"] == "7"
        assert result["params"]["Steps"] == "12"
        assert result["params"]["CFG"] == "4.0"


# ---------------------------------------------------------------------------
# SwarmUI metadata
# ---------------------------------------------------------------------------


class TestParseSwarmMetadata:
    def test_valid_sui_image_params(self):
        data = {
            "sui_image_params": {
                "prompt": "a cat",
                "negativeprompt": "bad quality",
                "seed": "42",
                "steps": "20",
                "cfgscale": "7.0",
                "sampler": "euler",
                "scheduler": "karras",
                "model": "sd_xl",
                "swarm_version": "2.0",
                "aspectratio": "1:1",
                "width": 1024,
                "height": 1024,
            }
        }
        result = _parse_swarm_metadata(json.dumps(data))
        assert result["tool"] == "SwarmUI"
        assert result["prompt"] == "a cat"
        assert result["negative_prompt"] == "bad quality"
        assert result["params"]["Seed"] == "42"
        assert result["params"]["Steps"] == "20"
        assert result["params"]["CFG"] == "7.0"
        assert result["params"]["Sampler"] == "euler"
        assert result["params"]["Scheduler"] == "karras"
        assert result["params"]["Model"] == "sd_xl"
        assert result["params"]["SwarmVersion"] == "2.0"
        assert result["params"]["AspectRatio"] == "1:1"
        assert result["params"]["Width"] == "1024"
        assert result["params"]["Height"] == "1024"

    def test_lora_list_from_loras_and_loraweights(self):
        data = {
            "sui_image_params": {
                "prompt": "test",
                "loras": ["lora_a", {"model": "lora_b.safetensors", "weight": 0.8}],
                "loraweights": [1.0, 0.5],
            }
        }
        result = _parse_swarm_metadata(json.dumps(data))
        assert "lora_a:1.0" in result["params"]["Lora"]
        assert "lora_b:0.8" in result["params"]["Lora"]

    def test_lora_model_data_from_sui_models(self):
        data = {
            "sui_image_params": {"prompt": "test"},
            "sui_models": [
                {"name": "sdxl.safetensors", "param": "used_loras", "hash": "abc123"},
                {"name": "vae.safetensors", "param": "vae", "hash": "def456"},
            ],
        }
        result = _parse_swarm_metadata(json.dumps(data))
        assert "sdxl" in result["params"]["Lora"]
        assert len(result["models"]) == 2
        assert result["models"][0]["hash"] == "abc123"

    def test_sui_extra_date_generation_time_prep_time(self):
        data = {
            "sui_image_params": {"prompt": "test"},
            "sui_extra_data": {
                "date": "2026-01-15",
                "generation_time": 3.5,
            },
        }
        result = _parse_swarm_metadata(json.dumps(data))
        assert result["date"] == "2026-01-15"
        assert result["generation_time"] == 3.5

    def test_sui_extra_prep_time_fallback(self):
        data = {
            "sui_image_params": {"prompt": "test"},
            "sui_extra_data": {"prep_time": 1.2},
        }
        result = _parse_swarm_metadata(json.dumps(data))
        assert result["generation_time"] == 1.2

    def test_invalid_json_returns_none(self):
        assert _parse_swarm_metadata("not json") is None

    def test_non_swarm_json_returns_none(self):
        assert _parse_swarm_metadata('{"other": "data"}') is None

    def test_empty_string_returns_none(self):
        assert _parse_swarm_metadata("") is None


# ---------------------------------------------------------------------------
# NovelAI metadata
# ---------------------------------------------------------------------------


class TestParseNovelAIMetadata:
    def test_valid_novelai_json(self):
        data = {
            "Software": "NovelAI",
            "prompt": "masterpiece, 1girl, sunset",
            "negative_prompt": "low quality",
            "steps": 28,
            "sampler": "k_euler_ancestral",
            "seed": 987654321,
            "scale": 11.0,
            "model": "nai-diffusion-3",
        }
        result = _parse_novelai_metadata(json.dumps(data))
        assert result["tool"] == "NovelAI"
        assert result["prompt"] == "masterpiece, 1girl, sunset"
        assert result["negative_prompt"] == "low quality"
        assert result["params"]["Seed"] == "987654321"
        assert result["params"]["Steps"] == "28"
        assert result["params"]["Sampler"] == "k_euler_ancestral"
        assert result["params"]["CFG"] == "11.0"
        assert result["params"]["Model"] == "nai-diffusion-3"

    def test_lora_extraction_from_prompt_text(self):
        data = {
            "Software": "NovelAI",
            "prompt": "1girl <lora:style_a:0.5>",
            "negative_prompt": "bad <lora:anti:0.3>",
        }
        result = _parse_novelai_metadata(json.dumps(data))
        assert "style_a:0.5" in result["params"]["Lora"]
        assert "anti:0.3" in result["params"]["Lora"]

    def test_invalid_json_returns_none(self):
        assert _parse_novelai_metadata("invalid json") is None

    def test_non_novelai_json_returns_none(self):
        assert _parse_novelai_metadata('{"prompt": "test"}') is None

    def test_additional_fields_sm_sm_dyn_noise_schedule(self):
        data = {
            "Software": "NovelAI",
            "sm": True,
            "sm_dyn": False,
            "noise_schedule": "karras",
            "width": 832,
            "height": 1216,
            "cfg_rescale": 0.7,
        }
        result = _parse_novelai_metadata(json.dumps(data))
        assert result["params"]["sm"] == "True"
        assert result["params"]["noise_schedule"] == "karras"
        assert result["params"]["width"] == "832"
        assert result["params"]["cfg_rescale"] == "0.7"


# ---------------------------------------------------------------------------
# EasyDiffusion metadata
# ---------------------------------------------------------------------------


class TestParseEasyDiffusionMetadata:
    def test_valid_easydiffusion_json(self):
        data = {
            "prompt": "a painting of mountains",
            "negative_prompt": "blurry",
            "width": 512,
            "height": 512,
            "seed": 42,
            "steps": 50,
            "sampler": "plms",
            "cfg_scale": 12.0,
            "model": "sd_v1.5",
        }
        result = _parse_easydiffusion_metadata(json.dumps(data))
        assert result["tool"] == "EasyDiffusion"
        assert result["prompt"] == "a painting of mountains"
        assert result["negative_prompt"] == "blurry"
        assert result["params"]["Seed"] == "42"
        assert result["params"]["Steps"] == "50"
        assert result["params"]["Sampler"] == "plms"
        assert result["params"]["CFG"] == "12.0"
        assert result["params"]["Model"] == "sd_v1.5"

    def test_rejects_swarmui_json(self):
        data = {
            "sui_image_params": {"prompt": "test"},
            "prompt": "test",
            "negative_prompt": "",
            "width": 512,
            "height": 512,
        }
        result = _parse_easydiffusion_metadata(json.dumps(data))
        assert result is None

    def test_incomplete_json_missing_keys_returns_none(self):
        result = _parse_easydiffusion_metadata('{"prompt": "test"}')
        assert result is None

    def test_invalid_json_returns_none(self):
        assert _parse_easydiffusion_metadata("bad json") is None

    def test_lora_extraction_from_prompt(self):
        data = {
            "prompt": "landscape <lora:epic_style:0.9>",
            "negative_prompt": "ugly",
            "width": 768,
            "height": 768,
        }
        result = _parse_easydiffusion_metadata(json.dumps(data))
        assert "epic_style:0.9" in result["params"]["Lora"]


# ---------------------------------------------------------------------------
# _api_metadata_from_sources
# ---------------------------------------------------------------------------


class TestApiMetadataFromSources:
    def test_chooses_swarmui_from_parameters(self, tmp_path: Path):
        info = {
            "parameters": json.dumps({"sui_image_params": {"prompt": "swarm test"}}),
        }
        path = tmp_path / "dummy.png"
        result, raw = _api_metadata_from_sources(path, info)
        assert result["tool"] == "SwarmUI"
        assert result["prompt"] == "swarm test"
        assert raw

    def test_chooses_swarmui_from_usercomment(self, tmp_path: Path):
        info = {
            "UserComment": json.dumps({"sui_image_params": {"prompt": "swarm from exif"}}),
        }
        path = tmp_path / "dummy.png"
        result, _ = _api_metadata_from_sources(path, info)
        assert result["tool"] == "SwarmUI"

    def test_chooses_comfyui_from_prompt_workflow(self, tmp_path: Path):
        info = {
            "prompt": json.dumps(
                {
                    "1": {"inputs": {"text": "comfy prompt"}, "class_type": "CLIPTextEncode"},
                }
            ),
        }
        path = tmp_path / "dummy.png"
        result, _ = _api_metadata_from_sources(path, info)
        assert result["tool"] == "ComfyUI"

    def test_chooses_a1111_from_parameters_text(self, tmp_path: Path):
        info = {
            "parameters": "masterpiece, 1girl\nSteps: 20, Sampler: Euler, CFG scale: 7.0, Seed: 100, Model: test",
        }
        path = tmp_path / "dummy.png"
        result, _ = _api_metadata_from_sources(path, info)
        assert result["tool"] == "A1111"

    def test_chooses_novelai_from_parameters_json(self, tmp_path: Path):
        info = {
            "parameters": json.dumps(
                {
                    "Software": "NovelAI",
                    "prompt": "anime girl",
                    "steps": 28,
                    "sampler": "k_euler",
                    "seed": 555,
                    "scale": 11,
                    "model": "nai3",
                }
            ),
        }
        path = tmp_path / "dummy.png"
        result, _ = _api_metadata_from_sources(path, info)
        assert result["tool"] == "NovelAI"

    def test_falls_back_to_txt_sidecar(self, tmp_path: Path):
        png_path = tmp_path / "image.png"
        txt_path = tmp_path / "image.txt"
        txt_path.write_text("sidecar prompt\nSteps: 10, Sampler: DPM, Seed: 42, Model: sidecar_model")
        info = {}
        result, raw = _api_metadata_from_sources(png_path, info)
        assert result["tool"] == "A1111"
        assert result["prompt"] == "sidecar prompt"
        assert "sidecar_model" in raw

    def test_falls_back_to_generic_text_keys(self, tmp_path: Path):
        info = {
            "Description": "some description from metadata",
            "Software": "unknown tool v1",
        }
        path = tmp_path / "dummy.png"
        result, _ = _api_metadata_from_sources(path, info)
        assert result["tool"] == "Unknown"
        assert "description" in result["prompt"].lower() or "some" in result["prompt"]

    def test_returns_unknown_when_no_metadata_exists(self, tmp_path: Path):
        path = tmp_path / "dummy.png"
        result, _ = _api_metadata_from_sources(path, {})
        assert result["tool"] == "Unknown"
        assert result["prompt"] == ""


# ---------------------------------------------------------------------------
# extract_loras edge cases
# ---------------------------------------------------------------------------


class TestExtractLoras:
    def test_standard_lora_tags(self):
        text = "1girl <lora:detail:0.5> <lora:style:1.0>"
        loras = extract_loras(text)
        assert "detail:0.5" in loras
        assert "style:1.0" in loras

    def test_lora_without_weight(self):
        text = "<lora:my_lora>"
        loras = extract_loras(text)
        assert "my_lora" in loras

    def test_lora_bracket_style(self):
        text = "LoRA: [lora_a, lora_b, lora_c]"
        loras = extract_loras(text)
        assert "lora_a" in loras
        assert "lora_b" in loras
        assert "lora_c" in loras

    def test_no_lora_returns_empty(self):
        assert extract_loras("no lora here") == []

    def test_deduplicates(self):
        text = "<lora:dup:0.5> <lora:dup:0.5>"
        loras = extract_loras(text)
        assert len(loras) == 1


# ---------------------------------------------------------------------------
# parse_int / parse_float
# ---------------------------------------------------------------------------


class TestParseHelpers:
    def test_parse_int_valid(self):
        assert parse_int("42") == 42
        assert parse_int("  10  ") == 10

    def test_parse_int_invalid(self):
        assert parse_int("abc") is None
        assert parse_int(None) is None
        assert parse_int("") is None

    def test_parse_float_valid(self):
        assert parse_float("7.5") == 7.5
        assert parse_float(" 3.14 ") == 3.14

    def test_parse_float_invalid(self):
        assert parse_float("xyz") is None
        assert parse_float(None) is None
        assert parse_float([]) is None
