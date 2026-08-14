from pydantic import BaseModel


class BBox(BaseModel):
    page: int
    x: float
    y: float
    width: float
    height: float

    @classmethod
    def parse_coords(cls, coords: str | None) -> list["BBox"]:
        if not coords:
            return []

        boxes: list[BBox] = []
        for chunk in coords.split(";"):
            parts = chunk.split(",")
            if len(parts) != 5:
                continue
            try:
                page, x, y, width, height = parts
                boxes.append(
                    cls(
                        page=int(page),
                        x=float(x),
                        y=float(y),
                        width=float(width),
                        height=float(height),
                    )
                )
            except ValueError:
                continue
        return boxes
