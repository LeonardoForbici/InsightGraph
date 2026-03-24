"""Smoke test for deep_parser.py — run manually to verify."""
from deep_parser import DeepParser, _to_snake_case, VALID_KINDS
import tree_sitter_java as tsjava
from tree_sitter import Language, Parser

# snake_case
assert _to_snake_case("userId") == "user_id"
assert _to_snake_case("firstName") == "first_name"
assert _to_snake_case("columnName") == "column_name"
print("snake_case OK")

dp = DeepParser()

# signature hash
h = dp.compute_signature_hash("getUser", ["Long", "String"], "UserDTO")
assert len(h) == 64
assert h == dp.compute_signature_hash("getUser", ["Long", "String"], "UserDTO")
print("compute_signature_hash OK")

JAVA_LANGUAGE = Language(tsjava.language())
java_parser = Parser(JAVA_LANGUAGE)

java_code = b"""
public class UserController {
    @Column(name = "user_name")
    private String userName;

    @Id
    private Long id;

    private String email;

    public UserDTO getUser(@PathVariable Long userId, @RequestParam String filter) {
        return null;
    }

    public void create(@RequestBody UserDTO dto) {}
}
"""

tree = java_parser.parse(java_code)
root = tree.root_node

class_node = None
for child in root.children:
    if child.type == "class_declaration":
        class_node = child
        break

assert class_node is not None, "class node not found"

nodes, rels = dp.extract_java_field_nodes(
    class_node,
    "MyProject:src/UserController.java:UserController",
    "MyProject",
    "src/UserController.java",
)

print(f"Extracted {len(nodes)} nodes, {len(rels)} relationships")
for n in nodes:
    print(f"  {n['kind']:20s} {n['name']:20s} type={n['data_type']:15s} col={n['column_name']}")

for n in nodes:
    assert n["kind"] in VALID_KINDS, f"invalid kind: {n['kind']}"
    assert "parent_key" in n
    assert "namespace_key" in n

kinds = {n["name"]: n["kind"] for n in nodes}
assert kinds.get("userName") == "jpa_column", f"userName kind: {kinds.get('userName')}"
assert kinds.get("id") == "jpa_id"
assert kinds.get("email") == "class_field"
assert kinds.get("userId") == "path_variable"
assert kinds.get("filter") == "request_param"
assert kinds.get("dto") == "request_body"

col_node = next(n for n in nodes if n["name"] == "userName")
assert col_node["column_name"] == "user_name", f"got: {col_node['column_name']}"

rel_types = {r["type"] for r in rels}
assert "HAS_FIELD" in rel_types
assert "HAS_PARAMETER" in rel_types

print("All assertions passed!")
