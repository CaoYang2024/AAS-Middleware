import aas_middleware
import time
import threading
import os
import cv2
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import uvicorn
import typing

# ========== 配置 ==========
PUBLISH_TO_LAN = True  # ← ← ← 控制是否发布到局域网

CAMERA_INDEXES = [0, 1]
caps = [cv2.VideoCapture(i) for i in CAMERA_INDEXES]

# ========== 传感器类 ==========
class Sensor(aas_middleware.Submodel):
    sensor_type: str
    manufacturer: str
    frame_rate: typing.Optional[float] = None
    resolution: typing.Optional[str] = None
    bitrate: typing.Optional[str] = None
    aspect_ratio: typing.Optional[float] = None
    lightness: typing.Optional[float] = None
    brightness: typing.Optional[float] = None
    hue: typing.Optional[float] = None
    saturation: typing.Optional[float] = None

class Camera(Sensor):
    built_in_microphone: str
    built_in_speaker: str
    stream_type: str
    image_mode: str
    webcam_megapixels: float
    video_standard: str
    png_file_size: str
    jpeg_file_size: str
    number_of_colors: int
    average_rgb_color: str
    luminosity: typing.Optional[float] = None

class Lidar(Sensor):
    range: float

class SDV(aas_middleware.AAS):
    camera: Camera
    lidar: Lidar

example_sdv = SDV(
    id="SoftwareDefinedVehicle",
    id_short="SDV_ID",
    description="Software Defined Vehicle with Sensors",
    camera=Camera(
        id="camera_1",
        id_short="Camera_1_ID",
        description="Front Camera",
        sensor_type="Camera",
        manufacturer="GENERAL WEBCAM",
        built_in_microphone="None",
        built_in_speaker="None",
        frame_rate=25.0,
        resolution="1920x1080",
        bitrate="10.04 MB/s",
        aspect_ratio=1.78,
        lightness=53.73,
        brightness=53.59,
        hue=255,
        saturation=1.69,
        stream_type="video",
        image_mode="rgb",
        webcam_megapixels=2.07,
        video_standard="FHD",
        png_file_size="1.06 MB",
        jpeg_file_size="406.69 kB",
        number_of_colors=32697,
        average_rgb_color="gray",
        luminosity=53.13
    ),
    lidar=Lidar(
        id="lidar_1",
        id_short="Lidar_1_ID",
        description="Front Lidar",
        sensor_type="Lidar",
        manufacturer="Example Lidar Manufacturer",
        range=100.0
    ),
)

# ========== AAS Middleware ==========
data_model = aas_middleware.DataModel.from_models(example_sdv)
middleware = aas_middleware.Middleware()
middleware.load_data_model("sdv", data_model, persist_instances=True)
middleware.generate_rest_api_for_data_model("sdv")
middleware.generate_graphql_api_for_data_model("sdv")

app = middleware.app  # 继承 FastAPI app

# ========== 视频流处理函数 ==========
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

# ========== 路由定义 ==========
@app.get("/sdv/camera0/video_feed")
def video_feed_0():
    return StreamingResponse(generate_frames(0), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/sdv/camera1/video_feed")
def video_feed_1():
    return StreamingResponse(generate_frames(1), media_type="multipart/x-mixed-replace; boundary=frame")

# ========== 启动服务 ==========
if __name__ == "__main__":
    HOST = "0.0.0.0" if PUBLISH_TO_LAN else "127.0.0.1"
    PORT = 8000
    print(f"🚀 视频服务启动中：{'局域网发布' if PUBLISH_TO_LAN else '本地发布'}，访问地址：http://{HOST}:{PORT}/sdv/camera0/video_feed")
    uvicorn.run(app, host=HOST, port=PORT)
