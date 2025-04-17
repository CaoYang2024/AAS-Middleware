import typing
import cv2
import aas_middleware
from fastapi.responses import StreamingResponse
import uvicorn

# ========== 配置 ==========
PUBLISH_TO_LAN = True
CAMERA_INDEXES = [0, 1]  # CSI 是 0，USB 是 1
caps = [cv2.VideoCapture(i) for i in CAMERA_INDEXES]

# ========== 自定义子模型结构 ==========
class Video(aas_middleware.SubmodelElementCollection):
    URL: str

class GeneralInfo(aas_middleware.Submodel):
    data_info: Video
    manufacterer: str
    product_type: str

class ProcessModel(aas_middleware.Submodel):
    processes: typing.List[str]

class Camera(aas_middleware.AAS):
    basic_info: GeneralInfo
    process_model: typing.Optional[ProcessModel]

# ========== CSI 摄像头 AAS ==========
csi_camera = Camera(
    id="csi_camera",
    id_short="camera_csi",
    description="CSI camera on Raspberry Pi",
    basic_info=GeneralInfo(
        id="general_info_csi",
        id_short="GeneralInfoCSI",
        description="CSI camera info",
        manufacterer="Raspberry Pi",
        product_type="csi_camera",
        data_info=Video(
            id="video_csi",
            id_short="VideoCSI",
            description="Video stream CSI",
            URL="http://192.168.31.160:8000/camera_csi/video_feed"
        ),
    ),
    process_model=ProcessModel(
        id="process_model_csi",
        id_short="ProcessCSI",
        description="Process for CSI",
        processes=["recording", "streaming"]
    )
)

# ========== USB 摄像头 AAS ==========
usb_camera = Camera(
    id="usb_camera",
    id_short="camera_usb",
    description="USB camera connected to Raspberry Pi",
    basic_info=GeneralInfo(
        id="general_info_usb",
        id_short="GeneralInfoUSB",
        description="USB camera info",
        manufacterer="Generic USB",
        product_type="usb_camera",
        data_info=Video(
            id="video_usb",
            id_short="VideoUSB",
            description="Video stream USB",
            URL="http://192.168.31.160:8000/camera_usb/video_feed"
        ),
    ),
    process_model=ProcessModel(
        id="process_model_usb",
        id_short="ProcessUSB",
        description="Process for USB",
        processes=["monitoring", "streaming"]
    )
)

# ========== AAS Middleware ==========
data_model_csi = aas_middleware.DataModel.from_models(csi_camera)
data_model_usb = aas_middleware.DataModel.from_models(usb_camera)

middleware = aas_middleware.Middleware()
middleware.load_data_model("camera_csi", data_model_csi, persist_instances=True)
middleware.load_data_model("camera_usb", data_model_usb, persist_instances=True)

middleware.generate_rest_api_for_data_model("camera_csi")
middleware.generate_rest_api_for_data_model("camera_usb")
middleware.generate_graphql_api_for_data_model("camera_csi")
middleware.generate_graphql_api_for_data_model("camera_usb")
app = middleware.app
print(middleware.data_models.keys())  # 是否含 "camera_usb"
# ========== 视频流处理 ==========
def generate_frames(cam_index: int):
    cap = caps[cam_index]
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# ========== 视频流路由 ==========
@app.get("/camera_csi/video_feed")
def video_feed_csi():
    return StreamingResponse(generate_frames(0), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/camera_usb/video_feed")
def video_feed_usb():
    return StreamingResponse(generate_frames(1), media_type="multipart/x-mixed-replace; boundary=frame")

# ========== 启动服务 ==========
if __name__ == "__main__":
    HOST = "0.0.0.0" if PUBLISH_TO_LAN else "127.0.0.1"
    PORT = 8000
    print("🚀 视频与 AAS 服务已启动：")
    print(f"  - CSI 视频流: http://{HOST}:{PORT}/camera_csi/video_feed")
    print(f"  - CSI AAS信息: http://{HOST}:{PORT}/camera_csi/")
    print(f"  - USB 视频流: http://{HOST}:{PORT}/camera_usb/video_feed")
    print(f"  - USB AAS信息: http://{HOST}:{PORT}/camera_usb/")
    uvicorn.run(app, host=HOST, port=PORT)
