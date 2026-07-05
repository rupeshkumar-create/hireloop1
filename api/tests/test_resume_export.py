from hireloop_api.services.resume_export import html_resume_to_docx


def test_html_resume_to_docx_produces_bytes() -> None:
    html = """
    <h1>Asha Rao</h1>
    <p class="resume-contact">Bengaluru · asha@example.com</p>
    <h2>Professional Summary</h2>
    <p>Category leader with 10+ years in retail.</p>
    <h2>Professional Experience</h2>
    <h3>Category Manager — Acme Retail</h3>
    <p class="role-meta">Jan 2020 – Present</p>
    <ul><li>Grew revenue 18% YoY</li><li>Led team of 6</li></ul>
    """
    data = html_resume_to_docx(html, title="Asha Rao")
    assert isinstance(data, bytes)
    assert len(data) > 1000
    assert data[:2] == b"PK"  # docx zip header
