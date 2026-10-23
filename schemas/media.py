from pydantic import BaseModel, Field


class ImageUploadRequest(BaseModel):
    data_url: str = Field(..., min_length=32, max_length=8_000_000)
    filename: str = Field("image", max_length=160)


class MediaUrlResponse(BaseModel):
    url: str
