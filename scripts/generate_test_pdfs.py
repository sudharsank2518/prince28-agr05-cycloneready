from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "test_corpus" / "pdfs"


DOCUMENTS = [
    (
        "Cyclone Preparedness Guide",
        "Before a Cyclone",
        (
            "Prepare an emergency kit with drinking water, dry food, a torch, "
            "batteries, medicines and essential documents."
        ),
        (
            "Families should identify a safe shelter, discuss evacuation "
            "routes and monitor official weather bulletins."
        ),
    ),
    (
        "Coastal Evacuation Handbook",
        "Evacuation Planning",
        (
            "Coastal communities should understand local evacuation routes "
            "and the locations of designated relief shelters."
        ),
        (
            "Residents should follow instructions from local authorities "
            "and avoid returning until the area is declared safe."
        ),
    ),
    (
        "Flood Safety and Response",
        "Flood Risk Reduction",
        (
            "Flood water can conceal open drains, damaged roads and electrical "
            "hazards. Avoid walking or driving through flood water."
        ),
        (
            "Move important documents and essential supplies to a higher "
            "location when flooding is expected."
        ),
    ),
    (
        "Emergency Shelter Operations",
        "Shelter Management",
        (
            "A temporary shelter needs safe drinking water, sanitation, "
            "first aid, ventilation and accessible entry points."
        ),
        (
            "Shelter coordinators should maintain a registration list and "
            "communicate important updates to residents."
        ),
    ),
    (
        "Cyclone Warning Communication",
        "Warning Dissemination",
        (
            "Warnings should use clear language and explain the expected "
            "hazard, affected areas and recommended actions."
        ),
        (
            "Information should be shared through multiple channels so that "
            "people can receive updates during network disruptions."
        ),
    ),
    (
        "Community Disaster Response",
        "Community Preparedness",
        (
            "Community volunteers can help identify vulnerable residents, "
            "share verified warnings and support evacuation activities."
        ),
        ("Volunteers should work under the direction of authorized emergency response teams."),
    ),
    (
        "Post Cyclone Recovery Plan",
        "Initial Recovery",
        (
            "After a cyclone, inspect buildings carefully and stay away from "
            "damaged power lines and unstable structures."
        ),
        (
            "Record damage using photographs and written notes when it is "
            "safe to do so, and report urgent hazards to authorities."
        ),
    ),
    (
        "Emergency Medical Readiness",
        "First Aid Preparation",
        (
            "An emergency medical kit should include basic first aid supplies, "
            "gloves, clean dressings and necessary personal medication."
        ),
        (
            "People should seek qualified medical assistance for serious "
            "injuries and avoid untrained medical procedures."
        ),
    ),
    (
        "Weather Monitoring and Alerts",
        "Monitoring Procedures",
        (
            "Weather monitoring combines observations, forecasts and official "
            "warning bulletins to support preparedness decisions."
        ),
        (
            "A monitoring team should record the time and source of each "
            "update and communicate changes promptly."
        ),
    ),
    (
        "Disaster Preparedness for Schools",
        "School Safety",
        (
            "Schools should maintain emergency contacts, evacuation maps, "
            "attendance records and clearly marked assembly points."
        ),
        (
            "Practice drills help students and staff understand safe movement "
            "and emergency communication procedures."
        ),
    ),
]

TABLE_ROWS = [
    ["Activity", "Responsible team", "Priority"],
    ["Issue warning", "Local authority", "High"],
    ["Check shelter", "Response team", "High"],
    ["Share updates", "Community team", "Medium"],
]


def add_text(page, text, position, size=10.5, font="helv"):
    page.insert_text(position, text, fontsize=size, fontname=font)


def add_paragraph(page, text, rect, size=10.5):
    result = page.insert_textbox(
        rect,
        text,
        fontsize=size,
        fontname="helv",
        lineheight=1.35,
    )
    if result < 0:
        raise RuntimeError(f"Text did not fit on page: {text[:50]}")


def add_table(page, rows):
    x0, y0 = 55, 300
    col_widths = [155, 190, 100]
    row_height = 34
    x_positions = [x0]

    for width in col_widths:
        x_positions.append(x_positions[-1] + width)

    for row_index, row in enumerate(rows):
        y_top = y0 + row_index * row_height
        y_bottom = y_top + row_height

        for col_index, value in enumerate(row):
            rect = pymupdf.Rect(
                x_positions[col_index],
                y_top,
                x_positions[col_index + 1],
                y_bottom,
            )
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
            page.insert_textbox(
                pymupdf.Rect(
                    rect.x0 + 6,
                    rect.y0 + 9,
                    rect.x1 - 5,
                    rect.y1 - 4,
                ),
                value,
                fontsize=9.5,
                fontname="hebo" if row_index == 0 else "helv",
            )


def create_document(index, title, section, paragraph_one, paragraph_two):
    path = OUTPUT / f"cyclone_test_{index:02d}.pdf"
    document = pymupdf.open()
    document.set_metadata(
        {
            "title": title,
            "author": "CycloneReady College Project",
            "subject": "Original synthetic parser benchmarking document",
        }
    )

    # Page 1: title, heading and explanatory content.
    page = document.new_page()
    add_text(page, "CYCLONEREADY | TEST CORPUS", (55, 35), 8.5)
    add_text(page, title, (55, 85), 21, "hebo")
    add_text(page, section, (55, 135), 16, "hebo")
    add_paragraph(page, paragraph_one, pymupdf.Rect(55, 165, 540, 255))
    add_text(page, "Preparedness Principles", (55, 295), 14, "hebo")
    add_paragraph(page, paragraph_two, pymupdf.Rect(55, 320, 540, 405))
    add_paragraph(
        page,
        "This original document is part of a controlled college-project test "
        "corpus. Its content is illustrative and is not an official warning, "
        "forecast, emergency instruction or government publication.",
        pymupdf.Rect(55, 440, 540, 510),
        9.5,
    )
    add_text(page, f"Test document {index:02d} | Page 1", (55, 750), 8)

    # Page 2: another heading, table and explanatory text.
    page = document.new_page()
    add_text(page, "CYCLONEREADY | TEST CORPUS", (55, 35), 8.5)
    add_text(page, "Response Planning Table", (55, 85), 18, "hebo")
    add_paragraph(
        page,
        "The following table is sample planning data created to test "
        "structured table extraction. It does not represent an official "
        "operational assignment.",
        pymupdf.Rect(55, 110, 540, 180),
    )
    add_table(page, TABLE_ROWS)
    add_text(page, "Record Keeping", (55, 475), 14, "hebo")
    add_paragraph(
        page,
        "Teams should record the time of each action, the information "
        "received and any follow-up required. All decisions should be "
        "checked against current instructions from authorized authorities.",
        pymupdf.Rect(55, 500, 540, 610),
    )
    add_text(page, f"Test document {index:02d} | Page 2", (55, 750), 8)

    document.save(path, garbage=4, deflate=True)
    document.close()
    return path


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    for index, item in enumerate(DOCUMENTS, start=1):
        path = create_document(index, *item)
        print(f"Created: {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")

    print(f"\nGenerated {len(DOCUMENTS)} original PDF test documents.")
    print(f"Output folder: {OUTPUT}")


if __name__ == "__main__":
    main()
