import aas_middleware
import typing
import cv2
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import uvicorn

# ========== 摄像头配置 ==========
PUBLISH_TO_LAN = True
CAMERA_INDEXES = [0, 1]  # 0 是本地摄像头，1 是 USB 摄像头
caps = [cv2.VideoCapture(i) for i in CAMERA_INDEXES]

# ========== 定义传感器模型 ==========
class Sensor(aas_middleware.Submodel):
    sensor_type: str
    manufacturer: str
    frame_rate: typing.Optional[float] = None
    resolution: typing.Optional[str] = None

class Camera(Sensor):
    built_in_microphone: str
    built_in_speaker: str
    stream_type: str
    image_mode: str
    webcam_megapixels: float
    video_standard: str

class Lidar(Sensor):
    range: float

# ========== 创建三个独立的 AAS ==========
camera_local = aas_middleware.AAS(
    id="camera_local",
    id_short="CameraLocal",
    description="Local Camera Device",
    submodels=[
        Camera(
            id="camera_local_model",
            id_short="LocalCamModel",
            description="Local webcam (index 0)",
            sensor_type="Camera",
            manufacturer="GENERAL WEBCAM",
            frame_rate=25.0,
            resolution="1920x1080",
            built_in_microphone="None",
            built_in_speaker="None",
            stream_type="video",
            image_mode="rgb",
            webcam_megapixels=2.0,
            video_standard="FHD"
        )
    ]
)

camera_usb = aas_middleware.AAS(
    id="camera_usb",
    id_short="CameraUSB",
    description="USB Camera Device",
    submodels=[
        Camera(
            id="camera_usb_model",
            id_short="USBCamModel",
            description="USB webcam (index 1)",
            sensor_type="Camera",
            manufacturer="USB CAM INC",
            frame_rate=30.0,
            resolution="1280x720",
            built_in_microphone="Yes",
            built_in_speaker="None",
            stream_type="video",
            image_mode="rgb",
            webcam_megapixels=1.3,
            video_standard="HD"
        )
    ]
)

lidar_sensor = aas_middleware.AAS(
    id="lidar",
    id_short="LidarID",
    description="Lidar Sensor",
    submodels=[
        Lidar(
            id="lidar_model",
            id_short="LidarModel",
            description="Front Lidar",
            sensor_type="Lidar",
            manufacturer="Example Lidar Manufacturer",
            range=100.0
        )
    ]
)

# ========== 加载中间件 ==========
middleware = aas_middleware.Middleware()

# 将每个 AAS 注册到系统中
middleware.load_data_model("camera_local", aas_middleware.DataModel.from_models(camera_local))
middleware.load_data_model("camera_usb", aas_middleware.DataModel.from_models(camera_usb))
middleware.load_data_model("lidar", aas_middleware.DataModel.from_models(lidar_sensor))

# 生成 REST API
middleware.generate_rest_api_for_data_model("camera_local")
middleware.generate_rest_api_for_data_model("camera_usb")
middleware.generate_rest_api_for_data_model("lidar")

# 继承 FastAPI 应用
app = middleware.app

# ========== 视频流 ==========
def generate_frames(cam_index: int):
    cap = caps[cam_index]
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        else:
            _, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.get("/camera_local/video_feed")
def video_feed_local():
    return StreamingResponse(generate_frames(0), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/camera_usb/video_feed")
def video_feed_usb():
    return StreamingResponse(generate_frames(1), media_type="multipart/x-mixed-replace; boundary=frame")

# ========== 启动服务 ==========
if __name__ == "__main__":
    HOST = "0.0.0.0" if PUBLISH_TO_LAN else "127.0.0.1"
    PORT = 8000
    print(f"📡 AAS 服务运行中：http://{HOST}:{PORT}")
    print(f"🔴 视频流地址：")
    print(f"  → http://{HOST}:{PORT}/camera_local/video_feed")
    print(f"  → http://{HOST}:{PORT}/camera_usb/video_feed")
    uvicorn.run(app, host=HOST, port=PORT)
