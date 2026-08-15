import os
from fastapi.templating import Jinja2Templates

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

def render_template(name: str, context: dict, status_code: int = 200):
    request = context.get("request")
    if request is None:
        raise RuntimeError("Template context must include request")
    return Jinja2Templates.TemplateResponse(
        templates, request=request, name=name, context=context, status_code=status_code
    )
