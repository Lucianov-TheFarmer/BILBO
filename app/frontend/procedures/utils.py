# procedures/utils.py
import flet as ft

last_message = ""

def _find_listview_in_control(ctrl):
    """Busca recursiva por um ListView dentro de um controle."""
    try:
        if isinstance(ctrl, ft.ListView):
            return ctrl

        # verificar content (Container, Card, etc.)
        content = getattr(ctrl, "content", None)
        if content:
            lv = _find_listview_in_control(content)
            if lv:
                return lv

        # verificar controls (Column, Row, Page, ListView etc.)
        children = getattr(ctrl, "controls", None)
        if children:
            for c in children:
                lv = _find_listview_in_control(c)
                if lv:
                    return lv
    except Exception:
        return None
    return None

async def log_message(page, message, container_terminal=None):
    """
    Adiciona uma mensagem de log no ListView do terminal.

    Uso esperado (compatível com seu código atual):
        await log_message(page, message)
    Ou (quando você tem a referência do container):
        await log_message(page, message, container_terminal=container_terminal)
    """
    global last_message
    if message == last_message:
        return
    last_message = message

    listview = None

    # 1) se container_terminal foi passado diretamente, extrair seu ListView
    if container_terminal is not None:
        # container_terminal pode ser um Container cujo .content é o ListView,
        # ou pode ser o próprio ListView.
        if isinstance(container_terminal, ft.ListView):
            listview = container_terminal
        else:
            # tenta .content então busca recursivamente dentro
            content = getattr(container_terminal, "content", None)
            if isinstance(content, ft.ListView):
                listview = content
            else:
                listview = _find_listview_in_control(container_terminal)

    # 2) se não veio container_terminal, tenta encontrar referência em page (page.container_terminal)
    if listview is None:
        page_container = getattr(page, "container_terminal", None)
        if page_container is not None:
            if isinstance(page_container, ft.ListView):
                listview = page_container
            else:
                content = getattr(page_container, "content", None)
                if isinstance(content, ft.ListView):
                    listview = content
                else:
                    listview = _find_listview_in_control(page_container)

    # 3) fallback: procurar recursivamente no próprio page
    if listview is None:
        listview = _find_listview_in_control(page)

    # 4) se ainda não encontrou, registra no console (evita crash silencioso)
    if listview is None:
        print("log_message: não encontrou ListView do terminal. Mensagem:", message)
        return

    try:
        listview.controls.append(ft.Text(message))
        # atualizar a própria ListView evita condições em que page.update() não reflita
        # mas page.update() é seguro para garantir a atualização da UI.
        page.update()
    except Exception as e:
        print("log_message: erro ao adicionar mensagem ao terminal:", e)
