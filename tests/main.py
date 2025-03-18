from flet import *
from flethtml.converter import convert_html_to_flet

def main (page:Page):
    body_html = """
    <div>
        <h1>Hello from HTML now </h1>
        <p style="background-color:green;color:white">This my content</p>

        <a href="https://www.google.com">Google</a>
    </div>
    """

    code_html = convert_html_to_flet(body_html)
    page.add(code_html)

app(target=main)