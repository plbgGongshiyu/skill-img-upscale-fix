#!/usr/bin/env python
import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError as exc:
    raise SystemExit("requests is required. Install with: pip install requests") from exc

DEFAULT_BASE_URL = "https://www.runninghub.cn"
DEFAULT_UPLOAD_ENDPOINT = f"{DEFAULT_BASE_URL}/openapi/v2/media/upload/binary"
DEFAULT_CREATE_ENDPOINT = f"{DEFAULT_BASE_URL}/task/openapi/create"
DEFAULT_QUERY_V2_ENDPOINT = f"{DEFAULT_BASE_URL}/openapi/v2/query"
DEFAULT_REPAIR_WORKFLOW_ID = "1991362449412829185"
DEFAULT_LOSSLESS_WORKFLOW_ID = "2031989838488014849"
DEFAULT_REPAIR_WORKFLOW = os.path.join(os.path.dirname(__file__), "..", "references", "seedvr2_workflow_api.json")
DEFAULT_LOSSLESS_WORKFLOW = os.path.join(os.path.dirname(__file__), "..", "references", "seedvr2_lossless_workflow_api.json")

WORKFLOW_PRESETS: Dict[str, Dict[str, Optional[str]]] = {
    "repair": {
        "workflow_id": DEFAULT_REPAIR_WORKFLOW_ID,
        "workflow_path": DEFAULT_REPAIR_WORKFLOW,
        "load_image_node": "12",
        "resolution_node": "37",
        "seed_node": "28",
        "megapixels_node": "24",
    },
    "lossless": {
        "workflow_id": DEFAULT_LOSSLESS_WORKFLOW_ID,
        "workflow_path": DEFAULT_LOSSLESS_WORKFLOW,
        "load_image_node": "35",
        "resolution_node": "40",
        "seed_node": "45",
        "megapixels_node": None,
    },
}


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True)


def _find_first_key(payload: Any, keys: List[str]) -> Optional[Any]:
    if isinstance(payload, dict):
        for key in keys:
            if key in payload:
                return payload[key]
        for value in payload.values():
            found = _find_first_key(value, keys)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_first_key(item, keys)
            if found is not None:
                return found
    return None


def _find_reference(upload_json: Dict[str, Any]) -> Optional[str]:
    candidates = ["url", "fileUrl", "file_url", "fileName", "file_name", "fileKey", "file_key", "key"]
    value = _find_first_key(upload_json, candidates)
    if isinstance(value, str):
        return value
    return None


def _set_workflow_image(workflow: Dict[str, Any], image_ref: str, load_image_node: str) -> None:
    if load_image_node not in workflow:
        raise SystemExit(f"workflow node {load_image_node} not found; expected LoadImage node")
    workflow[load_image_node].setdefault("inputs", {})["image"] = image_ref


def _set_optional_values(
    workflow: Dict[str, Any],
    resolution: Optional[int],
    seed: Optional[int],
    megapixels: Optional[float],
    resolution_node: Optional[str],
    seed_node: Optional[str],
    megapixels_node: Optional[str],
) -> None:
    if resolution is not None:
        if not resolution_node:
            raise SystemExit("resolution is not supported for this workflow preset")
        if resolution_node not in workflow:
            raise SystemExit(f"workflow node {resolution_node} not found; expected resolution node")
        workflow[resolution_node].setdefault("inputs", {})["value"] = int(resolution)
    if seed is not None:
        if not seed_node:
            raise SystemExit("seed is not supported for this workflow preset")
        if seed_node not in workflow:
            raise SystemExit(f"workflow node {seed_node} not found; expected SeedVR2VideoUpscaler node")
        workflow[seed_node].setdefault("inputs", {})["seed"] = int(seed)
    if megapixels is not None:
        if not megapixels_node:
            raise SystemExit("megapixels is not supported for this workflow preset")
        if megapixels_node not in workflow:
            raise SystemExit(f"workflow node {megapixels_node} not found; expected ImageScaleToTotalPixels node")
        workflow[megapixels_node].setdefault("inputs", {})["megapixels"] = float(megapixels)


def _build_node_info_list(
    image_ref: str,
    resolution: Optional[int],
    seed: Optional[int],
    megapixels: Optional[float],
    load_image_node: str,
    resolution_node: Optional[str],
    seed_node: Optional[str],
    megapixels_node: Optional[str],
) -> List[Dict[str, Any]]:
    node_info_list: List[Dict[str, Any]] = [
        {"nodeId": load_image_node, "fieldName": "image", "fieldValue": image_ref},
    ]
    if resolution is not None:
        if not resolution_node:
            raise SystemExit("resolution is not supported for this workflow preset")
        node_info_list.append({"nodeId": resolution_node, "fieldName": "value", "fieldValue": str(int(resolution))})
    if seed is not None:
        if not seed_node:
            raise SystemExit("seed is not supported for this workflow preset")
        node_info_list.append({"nodeId": seed_node, "fieldName": "seed", "fieldValue": str(int(seed))})
    if megapixels is not None:
        if not megapixels_node:
            raise SystemExit("megapixels is not supported for this workflow preset")
        node_info_list.append({"nodeId": megapixels_node, "fieldName": "megapixels", "fieldValue": str(float(megapixels))})
    return node_info_list


def _upload_image(api_key: str, image_path: str, upload_url: str, upload_field: str, upload_response_field: Optional[str]) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    with open(image_path, "rb") as handle:
        files = {upload_field: (os.path.basename(image_path), handle)}
        response = requests.post(upload_url, headers=headers, files=files, timeout=120)
    response.raise_for_status()
    payload = response.json()
    if upload_response_field:
        current = payload
        for part in upload_response_field.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise SystemExit(f"upload response field not found: {upload_response_field}")
        if not isinstance(current, str):
            raise SystemExit(f"upload response field is not a string: {upload_response_field}")
        return current
    reference = _find_reference(payload)
    if not reference:
        raise SystemExit("could not locate upload reference in response; use --upload-response-field")
    return reference


def _create_task(
    api_key: str,
    workflow: Optional[Dict[str, Any]],
    create_url: str,
    workflow_id: Optional[str],
    node_info_list: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {"apiKey": api_key}
    if workflow is not None:
        body["workflow"] = workflow
    if workflow_id:
        body["workflowId"] = workflow_id
    if node_info_list:
        body["nodeInfoList"] = node_info_list
    response = requests.post(create_url, headers=headers, json=body, timeout=120)
    response.raise_for_status()
    return response.json()


def _query_task_v2(api_key: str, task_id: str, query_url: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {"taskId": task_id}
    response = requests.post(query_url, headers=headers, json=body, timeout=120)
    response.raise_for_status()
    return response.json()


def _extract_task_id(create_json: Dict[str, Any]) -> str:
    task_id = _find_first_key(create_json, ["taskId", "task_id"])
    if not task_id:
        raise SystemExit(f"taskId not found in create response: {json.dumps(create_json, ensure_ascii=True)}")
    return str(task_id)


def _extract_task_status(status_json: Dict[str, Any]) -> Optional[str]:
    status_value = _find_first_key(status_json, ["taskStatus", "task_status", "status"])
    if status_value is None:
        return None
    return str(status_value).upper()


def _extract_result_urls(query_json: Dict[str, Any]) -> List[str]:
    urls: List[str] = []
    results = query_json.get("results")
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                url = item.get("url")
                if isinstance(url, str) and url:
                    urls.append(url)
    if not urls:
        fallback = _find_first_key(query_json, ["url", "fileUrl", "imageUrl"])
        if isinstance(fallback, str) and fallback:
            urls.append(fallback)
    return urls


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Runninghub SeedVR2 image upscale workflow")
    parser.add_argument("--api-key", default=os.environ.get("RUNNINGHUB_API_KEY"), help="Runninghub API key")
    parser.add_argument("--image", required=True, help="Path to input image")
    parser.add_argument("--mode", choices=sorted(WORKFLOW_PRESETS.keys()), default="repair", help="Workflow preset")
    parser.add_argument("--workflow", default=None, help="Optional workflow JSON path override")
    parser.add_argument("--resolution", type=int, default=None, help="Optional target resolution node value")
    parser.add_argument("--seed", type=int, default=None, help="Optional seed override")
    parser.add_argument("--megapixels", type=float, default=None, help="Optional megapixels override")
    parser.add_argument("--workflow-id", default=None, help="Runninghub workflowId override")
    parser.add_argument(
        "--use-workflow",
        action="store_true",
        help="Send full workflow JSON even when workflow-id is provided",
    )
    parser.add_argument("--upload-url", default=DEFAULT_UPLOAD_ENDPOINT)
    parser.add_argument("--create-url", default=DEFAULT_CREATE_ENDPOINT)
    parser.add_argument("--query-url", default=DEFAULT_QUERY_V2_ENDPOINT)
    parser.add_argument("--upload-field", default="file", help="Multipart field name for upload")
    parser.add_argument("--upload-response-field", default=None, help="Dot path to upload response field")
    parser.add_argument("--poll-interval", type=int, default=5, help="Seconds between status checks")
    parser.add_argument("--timeout", type=int, default=900, help="Max seconds to wait")
    parser.add_argument("--debug-save-workflow", default=None, help="Optional path to save patched workflow JSON")
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("API key missing. Provide --api-key or set RUNNINGHUB_API_KEY")
    if not os.path.isfile(args.image):
        raise SystemExit(f"image not found: {args.image}")

    preset = WORKFLOW_PRESETS[args.mode]
    workflow_id = args.workflow_id if args.workflow_id is not None else preset["workflow_id"]
    workflow_path = args.workflow if args.workflow is not None else preset["workflow_path"]
    load_image_node = str(preset["load_image_node"])
    resolution_node = preset["resolution_node"]
    seed_node = preset["seed_node"]
    megapixels_node = preset["megapixels_node"]

    image_ref = _upload_image(args.api_key, args.image, args.upload_url, args.upload_field, args.upload_response_field)

    workflow_payload: Optional[Dict[str, Any]] = None
    node_info_list: Optional[List[Dict[str, Any]]] = None

    if args.use_workflow or not workflow_id:
        workflow_payload = _load_json(str(workflow_path))
        _set_workflow_image(workflow_payload, image_ref, load_image_node)
        _set_optional_values(
            workflow_payload,
            args.resolution,
            args.seed,
            args.megapixels,
            resolution_node,
            seed_node,
            megapixels_node,
        )

        if args.debug_save_workflow:
            _save_json(args.debug_save_workflow, workflow_payload)
    else:
        node_info_list = _build_node_info_list(
            image_ref,
            args.resolution,
            args.seed,
            args.megapixels,
            load_image_node,
            resolution_node,
            seed_node,
            megapixels_node,
        )

    create_json = _create_task(args.api_key, workflow_payload, args.create_url, workflow_id, node_info_list)
    task_id = _extract_task_id(create_json)

    start = time.time()
    status = None
    latest_query_json: Dict[str, Any] = {}
    output_urls: List[str] = []
    while True:
        latest_query_json = _query_task_v2(args.api_key, task_id, args.query_url)
        status = _extract_task_status(latest_query_json)
        output_urls = _extract_result_urls(latest_query_json)
        if status == "SUCCESS" and output_urls:
            break
        if status in {"FAILED", "ERROR", "CANCELED", "CANCELLED"}:
            break
        if time.time() - start > args.timeout:
            raise SystemExit(
                f"timeout waiting for task completion, last_status={status}, task_id={task_id}"
            )
        time.sleep(args.poll_interval)

    print(
        json.dumps(
            {
                "taskId": task_id,
                "status": status,
                "outputUrls": output_urls,
                "outputs": latest_query_json,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
