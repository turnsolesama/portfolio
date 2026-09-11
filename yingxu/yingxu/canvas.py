"""Validate portable Excalidraw documents without fetching remote content."""
import json
from .store import UserError, TEXT_LIMIT

EMPTY = json.dumps({'type':'excalidraw','version':2,'source':'YingXu','elements':[],
                    'appState':{'viewBackgroundColor':'#ffffff'},'files':{}},ensure_ascii=False)

def validate(content):
    if not isinstance(content,str) or len(content.encode('utf-8'))>TEXT_LIMIT:
        raise UserError('画板文件最多 2 MiB，请减少嵌入图片大小。')
    try: scene=json.loads(content)
    except (ValueError,RecursionError):raise UserError('画板不是有效的 Excalidraw JSON 文件。')
    if not isinstance(scene,dict) or scene.get('type')!='excalidraw' or scene.get('version')!=2:
        raise UserError('请选择标准 .excalidraw 画板文件（版本 2）。')
    elements=scene.get('elements');files=scene.get('files',{})
    if not isinstance(elements,list) or len(elements)>10000 or not isinstance(files,dict) or not isinstance(scene.get('appState',{}),dict):
        raise UserError('画板结构不正确，或超过 10000 个元素。')
    for element in elements:
        if not isinstance(element,dict) or element.get('type') in ('iframe','embeddable'):
            raise UserError('本地画板不支持网页嵌入元素。')
    for value in files.values():
        if not isinstance(value,dict) or not isinstance(value.get('dataURL'),str) or not value['dataURL'].startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,','data:image/gif;base64,')):
            raise UserError('画板图片须为内嵌 PNG、JPEG、WebP 或 GIF，不加载外部图片。')
    return content
