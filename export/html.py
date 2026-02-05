from pathlib import Path

def write_html_file(output_path: Path, html_content: str):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
