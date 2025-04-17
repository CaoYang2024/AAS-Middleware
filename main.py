import typing
import cv2
import aas_middleware
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import requests
import uvicorn

# ========== 配置 ==========
PUBLISH_TO_LAN = True
CSI_STREAM_URL = "http://127.0.0.1:8001"  # rpicam-vid 推流地址
USB_CAMERA_INDEX = 0

# 初始化 USB 摄像头
cap_usb = cv2.VideoCapture(USB_CAMERA_INDEX)


# ====== 通用子模型结构定义 ======

class BasicInfo(aas_middleware.Submodel):
    manufacturer: str
    model: str

class VideoInfo(aas_middleware.Submodel):
    url: str

# ====== 定义 CSI 摄像头 AAS ======

class CameraCSI(aas_middleware.AAS):
    basic_info: BasicInfo
    video: VideoInfo

camera_csi = CameraCSI(
    id="csi_camera",
    id_short="camera_csi",
    description="CSI camera AAS",
    basic_info=BasicInfo(
        id="csi_basic_info",
        id_short="basic_info",
        description="CSI camera basic info",
        manufacturer="Raspberry Pi",
        model="IMX219"
    ),
    video=VideoInfo(
        id="csi_video",
        id_short="video",
        description="CSI camera video stream",
        url="http://192.168.31.160:8000/camera_csi/video_feed"
    )
)

# ====== 定义 USB 摄像头 AAS ======

class CameraUSB(aas_middleware.AAS):
    basic_info: BasicInfo
    video: VideoInfo

camera_usb = CameraUSB(
    id="usb_camera",
    id_short="camera_usb",
    description="USB camera AAS",
    basic_info=BasicInfo(
        id="usb_basic_info",
        id_short="basic_info",
        description="USB camera basic info",
        manufacturer="Generic",
        model="Logitech C270"
    ),
    video=VideoInfo(
        id="usb_video",
        id_short="video",
        description="USB camera video stream",
        url="http://192.168.31.160:8000/camera_usb/video_feed"
    )
)
# ========== AAS Middleware ==========
data_model_csi = aas_middleware.DataModel.from_models(camera_csi)
data_model_usb = aas_middleware.DataModel.from_models(camera_usb)

middleware = aas_middleware.Middleware()
middleware.load_data_model("camera_csi", data_model_csi, persist_instances=True)
middleware.load_data_model("camera_usb", data_model_usb, persist_instances=True)

middleware.generate_rest_api_for_data_model("camera_csi")
middleware.generate_rest_api_for_data_model("camera_usb")
middleware.generate_graphql_api_for_data_model("camera_csi")
middleware.generate_graphql_api_for_data_model("camera_usb")

# 使用 middleware 的 app 实例
app: FastAPI = middleware.app

# ========== 视频流处理 ==========
def proxy_rpicam_stream():
    """转发 rpicam-vid 推送的 MJPEG 视频流"""
    with requests.get(CSI_STREAM_URL, stream=True) as r:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                yield chunk

def generate_usb_frames():
    """读取 USB 摄像头的帧并转换为 MJPEG"""
    while cap_usb.isOpened():
        success, frame = cap_usb.read()
        if not success:
            break
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# ========== 视频流路由 ==========
@app.get("/camera_csi/video_feed")
def generate_csi_rtsp_frames():
    cap = cv2.VideoCapture("rtsp://127.0.0.1:8554/stream1")  # 或者换成树莓派 IP
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.get("/camera_usb/video_feed")
def video_feed_usb():
    return StreamingResponse(generate_usb_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

# ========== 启动服务 ==========
if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8000
    print("🚀 视频与 AAS 服务已启动：")
    print(f"  - Swagger 接口文档: http://{HOST}:{PORT}/docs")
    print(f"  - CSI 视频流: http://{HOST}:{PORT}/camera_csi/video_feed")
    print(f"  - USB 视频流: http://{HOST}:{PORT}/camera_usb/video_feed")
    print(f"  - CSI AAS 字段: http://{HOST}:{PORT}/CameraCSI")
    print(f"  - USB AAS 字段: http://{HOST}:{PORT}/CameraUSB")
    uvicorn.run(app, host=HOST, port=PORT)
