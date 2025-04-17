import typing
import aas_middleware


class Video(aas_middleware.SubmodelElementCollection):
    URL:str
class GeneralInfo(aas_middleware.Submodel):
    data_info: Video
    manufacterer: str
    product_type: str


class ProcessModel(aas_middleware.Submodel):
    processes: typing.List[str]


class Camera(aas_middleware.AAS):
    basic_info: GeneralInfo
    process_model: typing.Optional[ProcessModel]

csi_camera = Camera(
    id="csi_camera",
    id_short="camera0",
    description="the csi camera in raspberry",
    basic_info=GeneralInfo(
        id="General information",
        id_short="GeneralInfo",
        description="basic information about the sensor camera",
        manufacterer="Raspberry pi",
        product_type="csi_camera",
        data_info=Video(
            id="sensor_data",
            id_short="Video",
            description="Camera sensor",
            URL="http://192.168.31.160:8000/sdv/camera0/video_feed"
        ),
    ),
    process_model=ProcessModel(
        id="process_model_id",
        id_short="process_model_id",
        description="Process Model",
        processes=["process_1", "process_2"],
    ),
)

data_model = aas_middleware.DataModel.from_models(csi_camera)
basyx_object_store = aas_middleware.formatting.BasyxFormatter().serialize(data_model)
formatter = aas_middleware.formatting.AasJsonFormatter()
json_aas = formatter.serialize(data_model)
middleware = aas_middleware.Middleware()
middleware.load_data_model("example", data_model, persist_instances=True)
middleware.generate_rest_api_for_data_model("example")
middleware.generate_graphql_api_for_data_model("example")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(middleware.app)