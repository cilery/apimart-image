import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from apimart_image_test_loader import load_common_module


common = load_common_module()


class ResolveApiKeyTests(unittest.TestCase):
    def test_resolve_api_key_prefers_cli(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(json.dumps({"api_key": "file-key"}), encoding="utf-8")
            value = common.resolve_api_key(
                cli_key="cli-key",
                env_key="env-key",
                config_path=config_path,
            )
            self.assertEqual(value, "cli-key")

    def test_resolve_api_key_uses_env_then_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(json.dumps({"api_key": "file-key"}), encoding="utf-8")
            self.assertEqual(
                common.resolve_api_key(cli_key=None, env_key="env-key", config_path=config_path),
                "env-key",
            )
            self.assertEqual(
                common.resolve_api_key(cli_key=None, env_key="", config_path=config_path),
                "file-key",
            )


class ModelValidationTests(unittest.TestCase):
    def test_supported_models_are_gpt_and_gemini_only(self):
        names = set(common.MODELS)
        self.assertIn("gpt-image-2", names)
        self.assertIn("gpt-image-2-official", names)
        self.assertIn("gemini-3.1-flash-image-preview", names)
        self.assertIn("gemini-3-pro-image-preview", names)
        self.assertNotIn("qwen-image-2.0", names)
        self.assertNotIn("flux-kontext-pro", names)
        self.assertNotIn("imagen-4.0-apimart", names)

    def test_gemini_3_1_flash_allows_many_inputs(self):
        common.validate_model_inputs("gemini-3.1-flash-image-preview", image_count=14, has_mask=False)
        with self.assertRaises(common.ApimartImageError):
            common.validate_model_inputs("gemini-3.1-flash-image-preview", image_count=15, has_mask=False)

    def test_gpt_image_2_rejects_mask(self):
        with self.assertRaises(common.ApimartImageError):
            common.validate_model_inputs("gpt-image-2", image_count=1, has_mask=True)

    def test_gpt_image_2_official_allows_mask(self):
        common.validate_model_inputs("gpt-image-2-official", image_count=1, has_mask=True)


class PayloadTests(unittest.TestCase):
    def test_build_generation_payload_for_gpt_image_2(self):
        payload, warnings = common.build_generation_payload(
            model_name="gpt-image-2",
            prompt="make a lighthouse poster",
            image_urls=["https://example.com/input.png"],
            options={
                "size": "1536x1024",
                "resolution": "2k",
                "official_fallback": True,
                "quality": "high",
                "n": 1,
            },
            extra_json=None,
        )
        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertEqual(payload["prompt"], "make a lighthouse poster")
        self.assertEqual(payload["image_urls"], ["https://example.com/input.png"])
        self.assertEqual(payload["size"], "1536x1024")
        self.assertEqual(payload["resolution"], "2k")
        self.assertTrue(payload["official_fallback"])
        self.assertEqual(payload["n"], 1)
        self.assertIn("quality", warnings[0])

    def test_build_generation_payload_for_gpt_image_2_official(self):
        payload, warnings = common.build_generation_payload(
            model_name="gpt-image-2-official",
            prompt="replace the background",
            image_urls=["https://example.com/input.png"],
            options={
                "size": "1024x1024",
                "resolution": "2K",
                "quality": "high",
                "background": "white",
                "moderation": "auto",
                "output_format": "png",
                "output_compression": 90,
                "n": 4,
                "mask_url": "https://example.com/mask.png",
            },
            extra_json=None,
        )
        self.assertFalse(warnings)
        self.assertEqual(payload["n"], 4)
        self.assertEqual(payload["mask_url"], "https://example.com/mask.png")
        self.assertEqual(payload["output_format"], "png")

    def test_build_generation_payload_for_gemini(self):
        payload, warnings = common.build_generation_payload(
            model_name="gemini-3.1-flash-image-preview",
            prompt="make a wide mountain panorama",
            image_urls=["https://example.com/ref.png"],
            options={
                "size": "21:9",
                "resolution": "4K",
                "n": 4,
            },
            extra_json='{"google_search": true}',
        )
        self.assertFalse(warnings)
        self.assertEqual(payload["n"], 4)
        self.assertEqual(payload["google_search"], True)

    def test_build_generation_payload_for_gemini_ignores_false_official_fallback_without_warning(self):
        payload, warnings = common.build_generation_payload(
            model_name="gemini-3.1-flash-image-preview",
            prompt="make a portrait",
            image_urls=[],
            options={
                "size": "1:1",
                "resolution": "1K",
                "official_fallback": False,
            },
            extra_json=None,
        )
        self.assertFalse(warnings)
        self.assertNotIn("official_fallback", payload)

    def test_extra_json_merges_into_payload(self):
        payload, _ = common.build_generation_payload(
            model_name="gemini-3-pro-image-preview",
            prompt="make it warmer",
            image_urls=[],
            options={},
            extra_json='{"seed": 7, "metadata": {"origin": "test"}}',
        )
        self.assertEqual(payload["seed"], 7)
        self.assertEqual(payload["metadata"]["origin"], "test")

    def test_extract_result_urls_handles_gpt_image_2_shape(self):
        payload = {
            "data": {
                "status": "completed",
                "result": {
                    "images": [
                        {
                            "url": ["https://upload.apimart.ai/f/image/example.png"],
                        }
                    ]
                },
            }
        }
        self.assertEqual(
            common.extract_result_image_urls(payload),
            ["https://upload.apimart.ai/f/image/example.png"],
        )


class BatchTests(unittest.TestCase):
    def test_load_batch_file_requires_array(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.json"
            path.write_text(json.dumps({"prompt": "nope"}), encoding="utf-8")
            with self.assertRaises(common.ApimartImageError):
                common.load_batch_tasks(path)

    def test_choose_output_path_uses_slug_and_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = common.choose_output_path(
                output=None,
                output_dir=Path(temp_dir),
                prompt="Golden Retriever Portrait",
                index=0,
                extension=".png",
            )
            self.assertTrue(path.name.endswith("_golden-retriever-portrait.png"))


class TaskCreationResponseTests(unittest.TestCase):
    def test_create_generation_task_accepts_list_response(self):
        client = common.ApimartClient(base_url="https://api.apimart.ai", api_key="sk-test")
        try:
            response = Mock()
            response.status_code = 200
            response.json.return_value = [{"task_id": "task_123"}]
            client._request = Mock(return_value=response)
            task_id, body = client.create_generation_task({"model": "gpt-image-2", "prompt": "x"}, retries=0)
            self.assertEqual(task_id, "task_123")
            self.assertEqual(body, [{"task_id": "task_123"}])
        finally:
            client.close()

    def test_create_generation_task_accepts_data_list_response(self):
        client = common.ApimartClient(base_url="https://api.apimart.ai", api_key="sk-test")
        try:
            response = Mock()
            response.status_code = 200
            response.json.return_value = {
                "code": 200,
                "data": [{"status": "submitted", "task_id": "task_456"}],
            }
            client._request = Mock(return_value=response)
            task_id, body = client.create_generation_task({"model": "gpt-image-2", "prompt": "x"}, retries=0)
            self.assertEqual(task_id, "task_456")
            self.assertEqual(body["code"], 200)
        finally:
            client.close()


class UploadRequestTests(unittest.TestCase):
    def test_client_builds_multipart_request_for_uploads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "input.png"
            image_path.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            )
            client = common.ApimartClient(base_url="https://api.apimart.ai", api_key="sk-test")
            try:
                raw, mime_type = common.read_local_image(image_path)
                request = client._client.build_request(
                    "POST",
                    "https://api.apimart.ai/v1/uploads/images",
                    headers={"Authorization": "Bearer sk-test"},
                    files={"file": (image_path.name, raw, mime_type)},
                )
                self.assertIn("multipart/form-data", request.headers["content-type"])
            finally:
                client.close()


if __name__ == "__main__":
    unittest.main()
