import asyncio
from tools.s2v_client import S2VClient

async def main():
    client = S2VClient(
        base_url="https://x2v.light-ai.top",
        # access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoicGhvbmVfMTg4MTA3Mzk3MTUiLCJ1c2VybmFtZSI6IjE4ODEwNzM5NzE1IiwiZW1haWwiOiIiLCJob21lcGFnZSI6IiIsInRva2VuX3R5cGUiOiJhY2Nlc3MiLCJpYXQiOjE3NjkxNTQxNzMsImV4cCI6MTc2OTc1ODk3MywianRpIjoiYmQzMGZmNDMtZDFiOS00ZWU5LTgxN2MtZDYxMjMwYTk1YTI2In0._2S4bg9vGztHMJIecPcGtwKTJ7NpgEe6HPUed6y8kpU"
        access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoicGhvbmVfMTg4MTA3Mzk3MTUiLCJ1c2VybmFtZSI6IjE4ODEwNzM5NzE1IiwiZW1haWwiOiIiLCJob21lcGFnZSI6IiIsInRva2VuX3R5cGUiOiJhY2Nlc3MiLCJpYXQiOjE3NjkxNTk2ODEsImV4cCI6MTc2OTc2NDQ4MSwianRpIjoiNjMzYjgyOTQtNzQwYi00OTg2LWFmYWUtYTNmMjAwYWQ3YTU4In0.V0IS2aQeCML7j4cxoJAX1ISu0_BnA-Ae4k-8O4ruDzI"
    )
    try:
        submit = await client.submit_task(
            task="s2v",
            model_cls="SekoTalk",
            stage="single_stage",
            prompt="根据音频生成对应视频",
            negative_prompt="色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走",
            cfg_scale=5,
            duration=7,
            seed=1785815974737118556,
            input_image_path="/Users/qinxinyi/Documents/code/example/Generated Image October 17, 2025 - 1_35PM.png",
            input_audio_path="/Users/qinxinyi/Documents/code/example/lufei_v1.wav"
        )
        if not submit.get("success"):
            print("submit failed:", submit.get("error"))
            return

        task_id = submit["task_id"]
        final = await client.wait_for_task(task_id, poll_interval=5, timeout=3600)
        if not final.get("success"):
            print("query failed:", final.get("error"))
            return

        status = final.get("status")
        print("task status:", status)
        if status == "SUCCEED":
            result_url = await client.get_result_url(task_id, name="output_video")
            print("video url:", result_url)
    finally:
        client.close()

asyncio.run(main())