from pydantic import BaseModel, Field

class Structure(BaseModel):
    title_zh: str = Field(description="faithful and complete Chinese translation of the paper title")
    abstract_zh: str = Field(description="faithful and complete Chinese translation of the arXiv abstract")
