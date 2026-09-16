"""Build tests/fixtures/jbig2_min.pdf.

A minimal JBIG2 PDF, coded with MMR (T.6) so no arithmetic coder is needed.
The bitmap is inverted before encoding because JBIG2's MMR convention runs
opposite to what Pillow emits.

Run: python scripts/make_jbig2_fixture.py
"""

import io
import pathlib
import struct

import pikepdf
from PIL import Image, TiffImagePlugin
from pikepdf import Dictionary, Name

TiffImagePlugin.STRIP_SIZE = 2 ** 28
W = H = 64
OUT = pathlib.Path(__file__).parent.parent / "tests" / "fixtures" / "jbig2_min.pdf"


def mmr_bytes(image):
    buf = io.BytesIO()
    image.save(buf, format="TIFF", compression="group4")
    tif = Image.open(io.BytesIO(buf.getvalue()))
    offsets, counts = tif.tag_v2[273], tif.tag_v2[279]
    assert len(offsets) == 1, "expected one strip, got %d" % len(offsets)
    return buf.getvalue()[offsets[0]:offsets[0] + counts[0]]


def segment(number, seg_type, page, data):
    head = struct.pack(">I", number)
    head += struct.pack(">B", seg_type & 0x3F)   # bit 6 clear: 1-byte page
    head += b"\x00"                              # no referred-to segments
    head += struct.pack(">B", page)
    head += struct.pack(">I", len(data))
    return head + data


def main():
    image = Image.new("1", (W, H), 0)
    for y in range(12, 52):
        for x in range(12, 52):
            if 18 <= x <= 22 or 18 <= y <= 22 or (x + y) % 17 == 0:
                image.putpixel((x, y), 1)
    mmr = mmr_bytes(image)

    page_info = struct.pack(">IIIIBH", W, H, 0, 0, 0x01, 0)   # 19 bytes
    region_info = struct.pack(">IIIIB", W, H, 0, 0, 0)        # 17 bytes
    generic = region_info + b"\x01" + mmr                     # MMR = 1
    stream = segment(0, 48, 1, page_info) + segment(1, 39, 1, generic)

    pdf = pikepdf.new()
    img = pdf.make_stream(stream)
    img.Type, img.Subtype = Name.XObject, Name.Image
    img.Width, img.Height = W, H
    img.ColorSpace, img.BitsPerComponent = Name.DeviceGray, 1
    img.Filter = Name.JBIG2Decode
    page = pdf.add_blank_page(page_size=(72, 72))
    page.Contents = pdf.make_stream(b"q 72 0 0 72 0 0 cm /Im0 Do Q")
    page.Resources = Dictionary(XObject=Dictionary(Im0=img))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(str(OUT))
    print("written:", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
