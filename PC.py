import cv2
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import aas_middleware
import uvicorn

# ===== 摄像头初始化 =====
cap = cv2.VideoCapture(0)  # PC摄像头索引通常是0

# ===== AAS结构定义 =====
class VideoInfo(aas_middleware.Submodel):
    url: str

class SimpleCameraAAS(aas_middleware.AAS):
    video: VideoInfo

camera_aas = SimpleCameraAAS(
    id="local_camera",
    id_short="camera_simple",
    description="Simple USB camera with stream URL",
    video=VideoInfo(
        id="video_info",
        id_short="video",
        description="Video stream info",
        url="http://localhost:8000/video_feed"
    )
)

# ===== AAS Middleware 初始化 =====
data_model = aas_middleware.DataModel.from_models(camera_aas)
middleware = aas_middleware.Middleware()
middleware.load_data_model("camera_simple", data_model, persist_instances=True)
middleware.generate_rest_api_for_data_model("camera_simple")

app: FastAPI = middleware.app  # 获取 FastAPI 应用实例

# ===== 视频流路由 =====
def generate_usb_stream():
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(generate_usb_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

# ===== 启动服务 =====
if __name__ == "__main__":
    print("🚀 AAS 视频流服务已启动")
    print("🔗 视频地址: http://localhost:8000/video_feed")
    uvicorn.run(app, host="0.0.0.0", port=8000)
