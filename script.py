import sys
sys.path.insert(0, 'backend')
from state_store import LocalStateStore
store = LocalStateStore('backend/insightgraph_state.db')
store.initialize()
print('tags:', store.list_tags())
print('annotations:', store.list_annotations())
