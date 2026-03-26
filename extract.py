from zipfile import ZipFile
from xml.etree import ElementTree as ET
path='InsightGraph_Implementation_Plan.docx'
with ZipFile(path) as docx:
    xml=docx.read('word/document.xml')
root=ET.fromstring(xml)
text=[]
for node in root.iter():
    if node.tag.endswith('}t'):
        text.append(node.text or '')
print('\n'.join(text))
