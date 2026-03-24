"""Debug tree-sitter AST structure for Java field declarations."""
import tree_sitter_java as tsjava
from tree_sitter import Language, Parser

JAVA_LANGUAGE = Language(tsjava.language())
java_parser = Parser(JAVA_LANGUAGE)

java_code = b"""
public class UserController {
    @Column(name = "user_name")
    private String userName;

    @Id
    private Long id;

    public UserDTO getUser(@PathVariable Long userId, @RequestParam String filter) {
        return null;
    }
}
"""

tree = java_parser.parse(java_code)
root = tree.root_node

def print_tree(node, indent=0):
    text = ""
    if node.child_count == 0:
        text = f" = {node.text.decode('utf-8')!r}"
    print(" " * indent + f"[{node.type}]{text}")
    for child in node.children:
        print_tree(child, indent + 2)

# Find class body
for child in root.children:
    if child.type == "class_declaration":
        for c in child.children:
            if c.type == "class_body":
                print("=== CLASS BODY MEMBERS ===")
                for member in c.children:
                    if member.type in ("field_declaration", "method_declaration"):
                        print(f"\n--- {member.type} ---")
                        print_tree(member, 2)
                        print(f"  child_by_field_name('modifiers') = {member.child_by_field_name('modifiers')}")
                        print(f"  prev_sibling = {member.prev_sibling}")
