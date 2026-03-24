"""
DeepParser — Field-level AST extraction for Java and Angular/TypeScript.

Extracts Field_Level_Nodes (parameters, class fields) from tree-sitter ASTs
and returns them as dicts following the Field_Level_Node schema.
"""

import re
import hashlib
from typing import Optional

import tree_sitter_java as tsjava
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser

JAVA_LANGUAGE = Language(tsjava.language())
_java_parser = Parser(JAVA_LANGUAGE)

TS_LANGUAGE = Language(tstypescript.language_typescript())
_ts_parser = Parser(TS_LANGUAGE)

# ──────────────────────────────────────────────
# Valid kind values for Field_Level_Nodes
# ──────────────────────────────────────────────
VALID_KINDS = {
    "path_variable",
    "request_param",
    "request_body",
    "jpa_column",
    "jpa_id",
    "jpa_many_to_one",
    "jpa_one_to_many",
    "jpa_join_column",
    "method_param",
    "class_field",
    # Angular kinds (added by extract_angular_bindings)
    "input_binding",
    "output_binding",
    "injected_dependency",
    # SQL kinds
    "procedure_param",
    "column_reference",
}

# Spring parameter annotations → kind
_SPRING_PARAM_ANNOTATIONS: dict[str, str] = {
    "PathVariable": "path_variable",
    "RequestParam": "request_param",
    "RequestBody": "request_body",
}

# JPA field annotations → kind
_JPA_FIELD_ANNOTATIONS: dict[str, str] = {
    "Column": "jpa_column",
    "Id": "jpa_id",
    "ManyToOne": "jpa_many_to_one",
    "OneToMany": "jpa_one_to_many",
    "JoinColumn": "jpa_join_column",
}


def _to_snake_case(name: str) -> str:
    """Convert a camelCase or PascalCase name to snake_case."""
    # Insert underscore before uppercase letters that follow lowercase letters or digits
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Insert underscore before uppercase letters that are followed by lowercase (handles acronyms)
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s1)
    return s2.lower()


def _get_annotation_name(annotation_node) -> str:
    """Extract the simple annotation name from an annotation node."""
    # annotation nodes have a child 'name' field or the name is the first identifier child
    name_node = annotation_node.child_by_field_name("name")
    if name_node:
        return name_node.text.decode("utf-8").strip()
    # fallback: first named child that is an identifier
    for child in annotation_node.children:
        if child.type == "identifier":
            return child.text.decode("utf-8").strip()
    return ""


def _get_annotation_attribute(annotation_node, attr: str) -> Optional[str]:
    """
    Extract the value of a named attribute from an annotation.
    E.g. @Column(name = "user_name") → attr="name" → "user_name"
    """
    for child in annotation_node.children:
        if child.type == "element_value_pair":
            key_node = child.child_by_field_name("key")
            val_node = child.child_by_field_name("value")
            if key_node and val_node and key_node.text.decode("utf-8").strip() == attr:
                val = val_node.text.decode("utf-8").strip().strip('"').strip("'")
                return val
        # Single-value annotation: @Column("user_name") — treat as 'name' attribute
        if child.type in ("string_literal", "character_literal") and attr == "name":
            return child.text.decode("utf-8").strip().strip('"').strip("'")
    return None


def _collect_modifiers_and_annotations(modifiers_node) -> tuple[list[str], list[str]]:
    """
    From a 'modifiers' tree-sitter node, collect:
    - modifiers: list of modifier keywords (public, private, static, final, …)
    - annotation_texts: list of raw annotation texts
    Returns (modifiers, annotation_texts).
    """
    modifiers: list[str] = []
    annotation_texts: list[str] = []
    if modifiers_node is None:
        return modifiers, annotation_texts
    for child in modifiers_node.children:
        if child.type in ("marker_annotation", "annotation"):
            annotation_texts.append(child.text.decode("utf-8"))
        elif child.type in (
            "public", "private", "protected", "static", "final",
            "abstract", "synchronized", "transient", "volatile", "native",
        ):
            modifiers.append(child.type)
    return modifiers, annotation_texts


def _get_modifiers_node_before(node) -> Optional[object]:
    """
    In tree-sitter Java, modifiers appear as the first child of the declaration
    node (field_declaration, method_declaration, formal_parameter).
    child_by_field_name("modifiers") may return None even when the node exists,
    so we scan children directly.
    """
    # Scan direct children for a modifiers node
    for child in node.children:
        if child.type == "modifiers":
            return child
    return None


class DeepParser:
    """
    Extracts Field_Level_Nodes from Java and Angular/TypeScript ASTs.

    Usage:
        parser = DeepParser()
        nodes, rels = parser.extract_java_field_nodes(class_node, class_ns_key, project, rel_path)
    """

    # ──────────────────────────────────────────────
    # Public helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _to_snake_case(name: str) -> str:
        return _to_snake_case(name)

    # ──────────────────────────────────────────────
    # Java extraction
    # ──────────────────────────────────────────────

    def extract_java_field_nodes(
        self,
        class_node,
        class_ns_key: str,
        project_name: str,
        rel_path: str,
    ) -> tuple[list[dict], list[dict]]:
        """
        Extract Field_Level_Nodes from a tree-sitter Java class node.

        Processes:
        - Class fields (JPA annotations: @Column, @Id, @ManyToOne, @OneToMany, @JoinColumn)
          from class_node's class body.
        - Method parameters (Spring annotations: @PathVariable, @RequestParam, @RequestBody)
          discovered automatically from method declarations inside the class body.

        Args:
            class_node:    tree-sitter node of the class declaration.
            class_ns_key:  namespace_key of the parent class.
            project_name:  project identifier.
            rel_path:      relative file path.

        Returns:
            (nodes, relationships) where each node follows the Field_Level_Node schema
            and each relationship is a dict with keys: type, from_key, to_key.

        Requirements: 1.1, 1.2, 1.3, 1.4
        """
        nodes: list[dict] = []
        relationships: list[dict] = []

        # ── 1. Find the class body ────────────────────────────────────────────
        class_body = None
        for child in class_node.children:
            if child.type == "class_body":
                class_body = child
                break

        if class_body is None:
            return nodes, relationships

        # ── 2. Extract class fields and method parameters from class body ─────
        for member in class_body.children:
            if member.type == "field_declaration":
                field_nodes, field_rels = self._extract_class_field(
                    member, class_ns_key, project_name, rel_path
                )
                nodes.extend(field_nodes)
                relationships.extend(field_rels)

            elif member.type == "method_declaration":
                param_nodes, param_rels = self._extract_method_params(
                    member, class_ns_key, project_name, rel_path
                )
                nodes.extend(param_nodes)
                relationships.extend(param_rels)

        return nodes, relationships

    # ──────────────────────────────────────────────
    # Private helpers — Java
    # ──────────────────────────────────────────────

    def _extract_class_field(
        self,
        field_node,
        class_ns_key: str,
        project_name: str,
        rel_path: str,
    ) -> tuple[list[dict], list[dict]]:
        """Extract a single class field declaration into Field_Level_Node(s)."""
        nodes: list[dict] = []
        relationships: list[dict] = []

        modifiers_node = _get_modifiers_node_before(field_node)
        modifiers, annotation_texts = _collect_modifiers_and_annotations(modifiers_node)

        # Determine kind from JPA annotations
        kind = "class_field"
        column_name_override: Optional[str] = None

        for child in (modifiers_node.children if modifiers_node else []):
            if child.type in ("marker_annotation", "annotation"):
                ann_name = _get_annotation_name(child)
                if ann_name in _JPA_FIELD_ANNOTATIONS:
                    kind = _JPA_FIELD_ANNOTATIONS[ann_name]
                    if ann_name == "Column":
                        column_name_override = _get_annotation_attribute(child, "name")
                    break  # use first matching JPA annotation

        # Get field type
        type_node = field_node.child_by_field_name("type")
        data_type = type_node.text.decode("utf-8").strip() if type_node else "unknown"

        # Get declarators (there may be multiple: int a, b;)
        for child in field_node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    continue
                field_name = name_node.text.decode("utf-8").strip()
                ns_key = f"{class_ns_key}:{field_name}"

                # column_name: annotation name attr, or snake_case of field name
                if kind == "jpa_column":
                    col_name = column_name_override if column_name_override else _to_snake_case(field_name)
                else:
                    col_name = _to_snake_case(field_name)

                node_dict = {
                    "namespace_key": ns_key,
                    "name": field_name,
                    "kind": kind,
                    "data_type": data_type,
                    "parent_key": class_ns_key,
                    "column_name": col_name,
                    "modifiers": modifiers,
                    "annotations": annotation_texts,
                    "project": project_name,
                    "file": rel_path,
                    "labels": ["Field_Level_Node"],
                }
                nodes.append(node_dict)
                relationships.append({
                    "type": "HAS_FIELD",
                    "from_key": class_ns_key,
                    "to_key": ns_key,
                })

        return nodes, relationships

    def _extract_method_params(
        self,
        method_node,
        class_ns_key: str,
        project_name: str,
        rel_path: str,
    ) -> tuple[list[dict], list[dict]]:
        """Extract parameters from a method declaration, deriving method_ns_key from class."""
        method_name_node = method_node.child_by_field_name("name")
        if method_name_node is None:
            return [], []
        method_name = method_name_node.text.decode("utf-8").strip()
        method_ns_key = f"{class_ns_key}.{method_name}"
        return self._extract_method_params_by_key(method_node, method_ns_key, project_name, rel_path)

    def _extract_method_params_by_key(
        self,
        method_node,
        method_ns_key: str,
        project_name: str,
        rel_path: str,
    ) -> tuple[list[dict], list[dict]]:
        """Extract parameters from a method declaration using an explicit method_ns_key."""
        nodes: list[dict] = []
        relationships: list[dict] = []

        params_node = method_node.child_by_field_name("parameters")
        if params_node is None:
            return nodes, relationships

        for param in params_node.children:
            if param.type != "formal_parameter":
                continue

            param_nodes, param_rels = self._extract_formal_parameter(
                param, method_ns_key, project_name, rel_path
            )
            nodes.extend(param_nodes)
            relationships.extend(param_rels)

        return nodes, relationships

    def _extract_formal_parameter(
        self,
        param_node,
        method_ns_key: str,
        project_name: str,
        rel_path: str,
    ) -> tuple[list[dict], list[dict]]:
        """Extract a single formal_parameter node."""
        nodes: list[dict] = []
        relationships: list[dict] = []

        # In tree-sitter Java, child_by_field_name("modifiers") returns None even
        # when a modifiers node exists — scan direct children instead.
        modifiers_node = _get_modifiers_node_before(param_node)
        modifiers, annotation_texts = _collect_modifiers_and_annotations(modifiers_node)

        # Determine kind from Spring annotations
        kind = "method_param"
        for child in (modifiers_node.children if modifiers_node else []):
            if child.type in ("marker_annotation", "annotation"):
                ann_name = _get_annotation_name(child)
                if ann_name in _SPRING_PARAM_ANNOTATIONS:
                    kind = _SPRING_PARAM_ANNOTATIONS[ann_name]
                    break

        # Type — child_by_field_name("type") may return None; scan children
        type_node = param_node.child_by_field_name("type")
        if type_node is None:
            for child in param_node.children:
                if child.type in ("type_identifier", "integral_type", "floating_point_type",
                                  "boolean_type", "void_type", "generic_type",
                                  "array_type", "scoped_type_identifier"):
                    type_node = child
                    break
        data_type = type_node.text.decode("utf-8").strip() if type_node else "unknown"

        # Name — child_by_field_name("name") may return None; last identifier child
        name_node = param_node.child_by_field_name("name")
        if name_node is None:
            # The parameter name is the last identifier in the node
            for child in reversed(param_node.children):
                if child.type == "identifier":
                    name_node = child
                    break
        if name_node is None:
            return nodes, relationships
        param_name = name_node.text.decode("utf-8").strip()

        ns_key = f"{method_ns_key}:{param_name}"

        node_dict = {
            "namespace_key": ns_key,
            "name": param_name,
            "kind": kind,
            "data_type": data_type,
            "parent_key": method_ns_key,
            "column_name": _to_snake_case(param_name),
            "modifiers": modifiers,
            "annotations": annotation_texts,
            "project": project_name,
            "file": rel_path,
            "labels": ["Field_Level_Node"],
        }
        nodes.append(node_dict)
        relationships.append({
            "type": "HAS_PARAMETER",
            "from_key": method_ns_key,
            "to_key": ns_key,
        })

        return nodes, relationships

    # ──────────────────────────────────────────────
    # Signature hash (task 1.3 — skeleton)
    # ──────────────────────────────────────────────

    def compute_signature_hash(
        self,
        method_name: str,
        param_types: list[str],
        return_type: str,
    ) -> str:
        """
        Compute SHA-256 of (method_name + sorted_param_types_joined + return_type)
        as a concatenated string.

        Returns a 64-character hex string.

        Requirements: 1.5, 2.8
        """
        sorted_params = "".join(sorted(param_types))
        payload = method_name + sorted_params + return_type
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ──────────────────────────────────────────────
    # Angular extraction (task 2.1 — skeleton)
    # ──────────────────────────────────────────────

    def extract_angular_bindings(
        self,
        class_node,
        class_ns_key: str,
        project_name: str,
        rel_path: str,
    ) -> tuple[list[dict], list[dict]]:
        """
        Extract @Input, @Output, injected dependencies and HTTP calls from
        an Angular/TypeScript class node.

        Args:
            class_node:    tree-sitter node of the TypeScript class_declaration.
            class_ns_key:  namespace_key of the parent class.
            project_name:  project identifier.
            rel_path:      relative file path.

        Returns:
            (nodes, relationships) where nodes are Field_Level_Node dicts and
            relationships are dicts with keys: type, from_key, to_key (plus
            optional http_method / url_pattern for CALLS_HTTP).

        Requirements: 3.1, 3.2, 3.3, 3.4
        """
        nodes: list[dict] = []
        relationships: list[dict] = []

        # ── 1. Detect Angular decorator on the class ──────────────────────────
        # In tree-sitter TS the decorator is a sibling BEFORE the class_declaration
        # inside the export_statement (or at program level).  We look at the
        # parent's children that precede this class_node.
        angular_type = self._detect_angular_type(class_node)

        # ── 2. Find the class body ────────────────────────────────────────────
        class_body = None
        for child in class_node.children:
            if child.type == "class_body":
                class_body = child
                break

        if class_body is None:
            return nodes, relationships

        # ── 3. Walk class body members ────────────────────────────────────────
        children = list(class_body.children)
        for i, member in enumerate(children):
            # ── 3a. @Input / @Output properties ──────────────────────────────
            if member.type == "public_field_definition":
                binding_nodes, binding_rels = self._extract_binding_property(
                    member, class_ns_key, project_name, rel_path, angular_type
                )
                nodes.extend(binding_nodes)
                relationships.extend(binding_rels)

            # ── 3b. Constructor → injected dependencies ───────────────────────
            elif member.type == "method_definition":
                name_node = member.child_by_field_name("name")
                if name_node and name_node.text.decode("utf-8").strip() == "constructor":
                    dep_nodes, dep_rels = self._extract_constructor_deps(
                        member, class_ns_key, project_name, rel_path, angular_type
                    )
                    nodes.extend(dep_nodes)
                    relationships.extend(dep_rels)

        # ── 4. Walk entire class body for HttpClient calls ────────────────────
        http_rels = self._extract_http_calls(class_body, class_ns_key)
        relationships.extend(http_rels)

        return nodes, relationships

    # ──────────────────────────────────────────────
    # Private helpers — Angular
    # ──────────────────────────────────────────────

    _ANGULAR_DECORATORS = {"Component", "Injectable", "Directive", "Pipe", "NgModule"}
    _HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}
    _HTTP_CLIENT_NAMES = {"http", "httpClient", "http_client", "_http", "_httpClient"}

    def _detect_angular_type(self, class_node) -> str:
        """
        Look for Angular decorator nodes that precede the class_declaration in
        its parent's children list.  Returns the decorator name (e.g. 'Component')
        or empty string if none found.
        """
        try:
            parent = class_node.parent
            if parent is None:
                return ""
            siblings = list(parent.children)
            class_idx = next(
                (i for i, c in enumerate(siblings) if c.id == class_node.id), -1
            )
            # Scan backwards from the class node looking for decorator siblings
            for sib in reversed(siblings[:class_idx]):
                if sib.type == "decorator":
                    name = self._decorator_name(sib)
                    if name in self._ANGULAR_DECORATORS:
                        return name
        except Exception:
            pass
        return ""

    def _decorator_name(self, decorator_node) -> str:
        """Extract the identifier name from a decorator node."""
        try:
            for child in decorator_node.children:
                if child.type == "identifier":
                    return child.text.decode("utf-8").strip()
                if child.type == "call_expression":
                    func = child.child_by_field_name("function")
                    if func and func.type == "identifier":
                        return func.text.decode("utf-8").strip()
        except Exception:
            pass
        return ""

    def _extract_binding_property(
        self,
        field_node,
        class_ns_key: str,
        project_name: str,
        rel_path: str,
        angular_type: str,
    ) -> tuple[list[dict], list[dict]]:
        """
        Extract a public_field_definition that has an @Input() or @Output()
        decorator as a child node.
        """
        nodes: list[dict] = []
        relationships: list[dict] = []

        # Collect decorator children of this field node
        binding_kind: Optional[str] = None
        for child in field_node.children:
            if child.type == "decorator":
                dec_name = self._decorator_name(child)
                if dec_name == "Input":
                    binding_kind = "input_binding"
                    break
                elif dec_name == "Output":
                    binding_kind = "output_binding"
                    break

        if binding_kind is None:
            return nodes, relationships

        # Property name — property_identifier child
        prop_name_node = field_node.child_by_field_name("name")
        if prop_name_node is None:
            for child in field_node.children:
                if child.type == "property_identifier":
                    prop_name_node = child
                    break
        if prop_name_node is None:
            return nodes, relationships

        prop_name = prop_name_node.text.decode("utf-8").strip()

        # Type annotation (optional)
        type_text = "unknown"
        type_ann = field_node.child_by_field_name("type")
        if type_ann is None:
            for child in field_node.children:
                if child.type == "type_annotation":
                    type_ann = child
                    break
        if type_ann is not None:
            raw = type_ann.text.decode("utf-8").strip()
            type_text = raw.lstrip(":").strip()

        ns_key = f"{class_ns_key}:{prop_name}"
        node_dict = {
            "namespace_key": ns_key,
            "name": prop_name,
            "kind": binding_kind,
            "data_type": type_text,
            "parent_key": class_ns_key,
            "angular_type": angular_type,
            "project": project_name,
            "file": rel_path,
            "labels": ["Field_Level_Node"],
        }
        nodes.append(node_dict)
        relationships.append({
            "type": "HAS_BINDING",
            "from_key": class_ns_key,
            "to_key": ns_key,
        })
        return nodes, relationships

    def _extract_constructor_deps(
        self,
        method_node,
        class_ns_key: str,
        project_name: str,
        rel_path: str,
        angular_type: str,
    ) -> tuple[list[dict], list[dict]]:
        """
        Extract constructor parameters as injected_dependency Field_Level_Nodes.
        """
        nodes: list[dict] = []
        relationships: list[dict] = []

        params_node = method_node.child_by_field_name("parameters")
        if params_node is None:
            return nodes, relationships

        for param in params_node.children:
            if param.type not in ("required_parameter", "optional_parameter"):
                continue

            # Parameter name — identifier child (skip accessibility_modifier)
            param_name_node = None
            for child in param.children:
                if child.type == "identifier":
                    param_name_node = child
                    break
            if param_name_node is None:
                continue
            param_name = param_name_node.text.decode("utf-8").strip()

            # Type annotation
            dep_type = "unknown"
            type_ann = param.child_by_field_name("type")
            if type_ann is None:
                for child in param.children:
                    if child.type == "type_annotation":
                        type_ann = child
                        break
            if type_ann is not None:
                raw = type_ann.text.decode("utf-8").strip()
                dep_type = raw.lstrip(":").strip()

            ns_key = f"{class_ns_key}:constructor:{param_name}"
            node_dict = {
                "namespace_key": ns_key,
                "name": param_name,
                "kind": "injected_dependency",
                "dependency_type": dep_type,
                "data_type": dep_type,
                "parent_key": class_ns_key,
                "angular_type": angular_type,
                "project": project_name,
                "file": rel_path,
                "labels": ["Field_Level_Node"],
            }
            nodes.append(node_dict)
            relationships.append({
                "type": "HAS_PARAMETER",
                "from_key": class_ns_key,
                "to_key": ns_key,
            })

        return nodes, relationships

    def _extract_http_calls(self, class_body_node, class_ns_key: str) -> list[dict]:
        """
        Walk the entire class body recursively looking for HttpClient call
        expressions of the form `this.http.get(url)` or `this.httpClient.post(url)`.

        Returns a list of CALLS_HTTP relationship dicts.
        """
        relationships: list[dict] = []
        self._walk_for_http_calls(class_body_node, class_ns_key, relationships)
        return relationships

    def _walk_for_http_calls(self, node, class_ns_key: str, acc: list[dict]) -> None:
        """Recursive DFS to find HttpClient call_expression nodes."""
        try:
            if node.type == "call_expression":
                rel = self._try_extract_http_call(node, class_ns_key)
                if rel is not None:
                    acc.append(rel)
                    return  # don't recurse into this call's children
            for child in node.children:
                self._walk_for_http_calls(child, class_ns_key, acc)
        except Exception:
            pass

    def _try_extract_http_call(self, call_node, class_ns_key: str) -> Optional[dict]:
        """
        If call_node matches `this.<httpName>.<method>(url, ...)`, return a
        CALLS_HTTP relationship dict; otherwise return None.

        Pattern (from AST exploration):
          call_expression
            member_expression          ← this.http.get
              call_expression | member_expression  ← this.http
              property_identifier      ← get / post / …
            arguments
              string | template_string ← url (first arg)
        """
        try:
            func_node = call_node.child_by_field_name("function")
            if func_node is None or func_node.type != "member_expression":
                return None

            # The method name (get, post, …)
            method_name_node = func_node.child_by_field_name("property")
            if method_name_node is None:
                return None
            method_name = method_name_node.text.decode("utf-8").strip().lower()
            if method_name not in self._HTTP_METHODS:
                return None

            # The object being called on must be `this.<httpName>`
            obj_node = func_node.child_by_field_name("object")
            if obj_node is None:
                return None

            if not self._is_http_client_member(obj_node):
                return None

            # Extract first string argument as url_pattern
            url_pattern = "unknown"
            args_node = call_node.child_by_field_name("arguments")
            if args_node is not None:
                for child in args_node.children:
                    if child.type == "string":
                        # Extract string_fragment child
                        for frag in child.children:
                            if frag.type == "string_fragment":
                                url_pattern = frag.text.decode("utf-8").strip()
                                break
                        if url_pattern == "unknown":
                            # fallback: strip quotes from full text
                            raw = child.text.decode("utf-8").strip()
                            url_pattern = raw.strip("'\"")
                        break
                    elif child.type == "template_string":
                        raw = child.text.decode("utf-8").strip()
                        url_pattern = raw.strip("`")
                        break
                    elif child.type not in ("(", ")", ","):
                        # Could be a variable — use its text
                        url_pattern = child.text.decode("utf-8").strip()
                        break

            return {
                "type": "CALLS_HTTP",
                "from_key": class_ns_key,
                "to_key": url_pattern,
                "http_method": method_name.upper(),
                "url_pattern": url_pattern,
            }
        except Exception:
            return None

    def _is_http_client_member(self, node) -> bool:
        """
        Return True if node represents `this.<httpClientName>` — i.e. a
        member_expression whose object is `this` and whose property is one of
        the known HttpClient field names.
        """
        try:
            if node.type == "member_expression":
                obj = node.child_by_field_name("object")
                prop = node.child_by_field_name("property")
                if obj and prop:
                    if obj.type == "this" and prop.text.decode("utf-8").strip() in self._HTTP_CLIENT_NAMES:
                        return True
        except Exception:
            pass
        return False
