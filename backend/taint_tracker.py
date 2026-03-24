"""
Taint Analysis Service - Rastreia fluxo de dados através do grafo
Integra-se com Tree-sitter parsers para extrair propriedades e DTOs
"""

from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class DataFlowNode:
    """Representa um ponto no fluxo de dados (propriedade, parâmetro, coluna)"""
    node_key: str
    name: str
    type_hint: str  # e.g., "string", "UserDTO", "Column"
    source: str    # "component", "controller", "service", "entity", "database"
    sensitive: bool = False  # Flag GDPR/LGPD


@dataclass
class DataFlowEdge:
    """Representa um fluxo entre dois pontos de dados"""
    from_key: str
    to_key: str
    flow_type: str  # "FLOWS_TO", "WRITES_TO_COLUMN", "READS_FROM_COLUMN", "TRANSFORMS"
    context: str = ""  # Contexto adicional (e.g., "method_call", "dto_mapping")


class TaintTracker:
    """Rastreia o fluxo de dados taint através de múltiplas camadas"""
    
    def __init__(self):
        self.flow_nodes: Dict[str, DataFlowNode] = {}
        self.flow_edges: List[DataFlowEdge] = []
    
    def extract_dto_properties(self, class_content: str, class_name: str, namespace_key: str) -> List[DataFlowNode]:
        """
        Extrai propriedades de DTOs/POJOs a partir do código-fonte.
        
        Exemplos:
        - Java: `private String email;`
        - TypeScript: `email: string;`
        """
        properties = []
        
        # Regex para Java properties
        java_pattern = r'(?:private|public|protected)?\s+(\w+)\s+(\w+)\s*[;=]'
        # Regex para TypeScript properties
        ts_pattern = r'(\w+)\s*:\s*(\w+)\s*[;=]'
        
        for match in re.finditer(java_pattern, class_content):
            prop_type, prop_name = match.groups()
            prop_key = f"{namespace_key}::PROPERTY::{prop_name}"
            is_sensitive = self._is_sensitive_property(prop_name)
            
            properties.append(DataFlowNode(
                node_key=prop_key,
                name=prop_name,
                type_hint=prop_type,
                source="entity" if "Entity" in class_name else "dto",
                sensitive=is_sensitive
            ))
        
        for match in re.finditer(ts_pattern, class_content):
            prop_name, prop_type = match.groups()
            prop_key = f"{namespace_key}::PROPERTY::{prop_name}"
            is_sensitive = self._is_sensitive_property(prop_name)
            
            properties.append(DataFlowNode(
                node_key=prop_key,
                name=prop_name,
                type_hint=prop_type,
                source="component" if ".tsx" in namespace_key or ".jsx" in namespace_key else "service",
                sensitive=is_sensitive
            ))
        
        return properties
    
    def extract_method_parameters(self, method_signature: str, method_key: str) -> List[DataFlowNode]:
        """
        Extrai parâmetros de métodos/funções.
        
        Exemplo: `getUserByEmail(String email, UserDTO user) -> List<User>`
        """
        parameters = []
        
        # Remover tipo de retorno (tudo antes do parêntese)
        match = re.search(r'\((.*?)\)', method_signature)
        if not match:
            return parameters
        
        params_str = match.group(1)
        if not params_str.strip():
            return parameters
        
        # Split por vírgula e processar cada parâmetro
        for param in params_str.split(','):
            param = param.strip()
            parts = param.split()
            if len(parts) >= 2:
                param_type = ' '.join(parts[:-1])  # Tudo menos o último token
                param_name = parts[-1]
                
                param_key = f"{method_key}::PARAM::{param_name}"
                is_sensitive = self._is_sensitive_property(param_name)
                
                parameters.append(DataFlowNode(
                    node_key=param_key,
                    name=param_name,
                    type_hint=param_type,
                    source="parameter",
                    sensitive=is_sensitive
                ))
        
        return parameters
    
    def track_dto_mapping(self, from_dto_key: str, to_dto_key: str, property_mappings: Dict[str, str]) -> List[DataFlowEdge]:
        """
        Rastreia o fluxo de dados entre DTOs (e.g., Frontend DTO -> Backend DTO -> DB Entity).
        
        property_mappings: {"email": "email", "user_name": "username"}
        """
        edges = []
        for from_prop, to_prop in property_mappings.items():
            from_key = f"{from_dto_key}::PROPERTY::{from_prop}"
            to_key = f"{to_dto_key}::PROPERTY::{to_prop}"
            
            edges.append(DataFlowEdge(
                from_key=from_key,
                to_key=to_key,
                flow_type="FLOWS_TO",
                context="dto_mapping"
            ))
        
        return edges
    
    def track_column_access(self, entity_key: str, method_type: str, columns: List[str], table: str) -> List[DataFlowEdge]:
        """
        Rastreia acesso a colunas da base de dados.
        
        method_type: "SELECT", "UPDATE", "DELETE", "INSERT"
        """
        edges = []
        flow_type = "READS_FROM_COLUMN" if method_type == "SELECT" else "WRITES_TO_COLUMN"
        
        for col in columns:
            col_key = f"database::{table}::COLUMN::{col}"
            edges.append(DataFlowEdge(
                from_key=entity_key if method_type != "SELECT" else col_key,
                to_key=col_key if method_type != "SELECT" else entity_key,
                flow_type=flow_type,
                context=f"{method_type} operation"
            ))
        
        return edges
    
    @staticmethod
    def _is_sensitive_property(name: str) -> bool:
        """Identifica propriedades sensíveis por nome"""
        sensitive_keywords = ["email", "password", "senha", "cpf", "ssn", "token", 
                            "apikey", "secret", "credit_card", "card_number", "cvv",
                            "birthdate", "birth_date", "private_key", "api_key"]
        name_lower = name.lower()
        return any(keyword in name_lower for keyword in sensitive_keywords)
    
    def get_flow_nodes_for_taint(self, start_key: str, graph_instance=None) -> List[str]:
        """
        Retorna todos os nós alcançáveis a partir de um ponto de taint.
        Essencial para responder: "Quais componentes são afetados por esta coluna?"
        
        Usa BFS para traversal.
        """
        if not graph_instance:
            return []
        
        visited = set()
        queue = [start_key]
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            # Query Neo4j para encontrar adjacentes
            query = """
            MATCH (n {namespace_key: $key})-[r:FLOWS_TO|WRITES_TO_COLUMN|READS_FROM_COLUMN]->(m)
            RETURN m.namespace_key AS neighbor
            """
            try:
                result = graph_instance.run(query, key=current)
                for record in result:
                    neighbor = record.get("neighbor")
                    if neighbor and neighbor not in visited:
                        queue.append(neighbor)
            except Exception:
                pass
        
        return list(visited)


# ──────────────────────────────────────────────
# Helpers para integração com parsers
# ──────────────────────────────────────────────

def extract_taint_from_typescript(content: str, file_path: str, namespace_key: str) -> Tuple[List[DataFlowNode], List[DataFlowEdge]]:
    """Hook para usar nos TS parsers"""
    tracker = TaintTracker()
    
    # Exemplo: Extrair interfaces e tipos
    interface_pattern = r'(interface|type)\s+(\w+)\s*(?:extends|=)?\s*\{([^}]+)\}'
    for match in re.finditer(interface_pattern, content):
        interface_name = match.group(2)
        interface_body = match.group(3)
        
        interface_key = f"{namespace_key}::INTERFACE::{interface_name}"
        props = tracker.extract_dto_properties(interface_body, interface_name, interface_key)
        tracker.flow_nodes.update({p.node_key: p for p in props})
    
    return list(tracker.flow_nodes.values()), tracker.flow_edges


def extract_taint_from_java(content: str, file_path: str, namespace_key: str) -> Tuple[List[DataFlowNode], List[DataFlowEdge]]:
    """Hook para usar nos Java parsers"""
    tracker = TaintTracker()
    
    # Extrair classe e suas propriedades
    class_pattern = r'(?:public|private)?\s*class\s+(\w+)\s*(?:extends|implements)?\s*[^{]*\{([^}]+)\}'
    
    for match in re.finditer(class_pattern, content):
        class_name = match.group(1)
        class_body = match.group(2)
        
        class_key = f"{namespace_key}::CLASS::{class_name}"
        props = tracker.extract_dto_properties(class_body, class_name, class_key)
        tracker.flow_nodes.update({p.node_key: p for p in props})
    
    # Extrair métodos e parâmetros
    method_pattern = r'(?:public|private)?\s+(?:static)?\s+(\w+(?:<[^>]+>)?)\s+(\w+)\s*\(([^)]*)\)'
    
    for match in re.finditer(method_pattern, content):
        return_type, method_name, params_str = match.groups()
        method_key = f"{namespace_key}::METHOD::{method_name}"
        
        # Parse parâmetros
        param_nodes = tracker.extract_method_parameters(f"({params_str})", method_key)
        tracker.flow_nodes.update({p.node_key: p for p in param_nodes})
    
    return list(tracker.flow_nodes.values()), tracker.flow_edges
