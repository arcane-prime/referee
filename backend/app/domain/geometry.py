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


# Notes
#
# GROBID returns element geometry as "page,x,y,width,height", joining multiple
# rectangles with ";" when an element wraps across lines.
#
# These are captured during extraction because they can only be produced while
# the PDF is being read, the same way source maps can only be produced during a
# build. They are what would later let the UI point at a citation inside the
# user's original file. Nothing in the pipeline depends on them, so a malformed
# rectangle is skipped rather than raised on: no parse should fail because a
# coordinate was unreadable.
