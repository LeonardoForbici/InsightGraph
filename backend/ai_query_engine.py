"""
AI Query Engine for natural language code queries.

This module provides natural language query capabilities using:
- RAG (Retrieval-Augmented Generation) for context retrieval
- Graph context building for dependency information
- Ollama integration for AI-powered responses
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional
import httpx

logger = logging.getLogger(__name__)


@dataclass
class CodeReference:
    """Reference to a specific code location."""
    file: str
    line: int
    snippet: str
    node_key: str


@dataclass
class AIQueryResponse:
    """Response from AI query."""
    answer: str
    relevant_nodes: List[str]
    references: List[CodeReference]
    confidence: float
    model: str


class AIQueryEngine:
    """
    Engine for processing natural language queries about code.
    
    Combines RAG search, graph context, and AI generation to provide
    comprehensive answers to code-related questions.
    """
    
    def __init__(
        self,
        neo4j_service,
        rag_store,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen3.5:4b"
    ):
        """
        Initialize AIQueryEngine.
        
        Args:
            neo4j_service: Neo4j service for graph queries
            rag_store: RAG store for document retrieval
            ollama_url: URL for Ollama API
            ollama_model: Model to use for generation
        """
        self.neo4j = neo4j_service
        self.rag_store = rag_store
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
    
    async def query(
        self,
        question: str,
        context_node: Optional[str] = None
    ) -> AIQueryResponse:
        """
        Process a natural language query about the code.
        
        Coordinates RAG search, graph context building, and AI generation
        to provide a comprehensive answer.
        
        Args:
            question: Natural language question
            context_node: Optional node key for context
        
        Returns:
            AI query response with answer and references
        
        Requirements:
            - 6.1: Main query entry point
            - 6.2: RAG context retrieval
            - 6.3: AI generation with Ollama
        """
        try:
            # Retrieve relevant documents from RAG
            rag_results = await self._retrieve_rag_context(question, limit=10)
            
            # Build graph context for relevant nodes
            graph_context = await self._build_graph_context(rag_results, limit=5)
            
            # Query Ollama for answer
            answer = await self._query_ollama(question, rag_results, graph_context)
            
            # Extract relevant nodes and references
            relevant_nodes = self._extract_relevant_nodes(rag_results)
            references = self._extract_references(answer, rag_results)
            
            # Calculate confidence
            confidence = self._calculate_confidence(rag_results, answer)
            
            return AIQueryResponse(
                answer=answer,
                relevant_nodes=relevant_nodes,
                references=references,
                confidence=confidence,
                model=self.ollama_model
            )
            
        except Exception as e:
            logger.error(f"AI query failed: {e}")
            return AIQueryResponse(
                answer="Sorry, I couldn't process your query. Please try again.",
                relevant_nodes=[],
                references=[],
                confidence=0.0,
                model=self.ollama_model
            )
    
    async def _retrieve_rag_context(
        self,
        question: str,
        limit: int = 10
    ) -> List[dict]:
        """
        Retrieve relevant documents from RAG store.
        
        Args:
            question: Query text
            limit: Maximum number of documents
        
        Returns:
            List of relevant documents
        
        Requirements:
            - 6.2: RAG context retrieval
        """
        try:
            # Use RAG store's search functionality
            results = self.rag_store.search(
                query=question,
                limit=limit,
                semantic=True
            )
            return results
        except Exception as e:
            logger.error(f"RAG retrieval failed: {e}")
            return []
    
    async def _build_graph_context(
        self,
        rag_results: List[dict],
        limit: int = 5
    ) -> str:
        """
        Build graph context for relevant nodes.
        
        Fetches impact data (upstream/downstream) for nodes found
        in RAG results.
        
        Args:
            rag_results: RAG search results
            limit: Maximum nodes to include
        
        Returns:
            Formatted graph context string
        
        Requirements:
            - 6.2: Graph context building
        """
        if not self.neo4j.is_connected:
            return ""
        
        context_lines = []
        node_keys = []
        
        # Extract node keys from RAG results
        for result in rag_results[:limit]:
            node_key = result.get('node_key') or result.get('namespace_key')
            if node_key and node_key not in node_keys:
                node_keys.append(node_key)
        
        # Build context for each node
        for node_key in node_keys[:limit]:
            try:
                # Get node info
                query = "MATCH (n:Entity {namespace_key: $key}) RETURN n"
                result = self.neo4j.graph.run(query, key=node_key).data()
                
                if result:
                    node = result[0]["n"]
                    context_lines.append(f"\nNode: {node.get('name', 'Unknown')}")
                    context_lines.append(f"  Type: {list(node.labels)[0] if node.labels else 'Unknown'}")
                    context_lines.append(f"  Complexity: {node.get('complexity', 'N/A')}")
                    
                    # Get upstream/downstream counts
                    impact_query = """
                    MATCH (n:Entity {namespace_key: $key})
                    OPTIONAL MATCH (n)-[]->(downstream)
                    OPTIONAL MATCH (upstream)-[]->(n)
                    RETURN count(DISTINCT downstream) AS down_count,
                           count(DISTINCT upstream) AS up_count
                    """
                    impact_result = self.neo4j.graph.run(impact_query, key=node_key).data()
                    
                    if impact_result:
                        context_lines.append(
                            f"  Dependencies: {impact_result[0]['down_count']} downstream, "
                            f"{impact_result[0]['up_count']} upstream"
                        )
            except Exception as e:
                logger.error(f"Failed to build context for {node_key}: {e}")
        
        return '\n'.join(context_lines)
    
    async def _query_ollama(
        self,
        question: str,
        rag_results: List[dict],
        graph_context: str
    ) -> str:
        """
        Query Ollama API for AI-generated answer.
        
        Args:
            question: User's question
            rag_results: RAG search results
            graph_context: Graph context string
        
        Returns:
            AI-generated answer
        
        Requirements:
            - 6.3: Ollama integration
        """
        try:
            # Build prompt with context
            code_context = "\n\n".join([
                f"File: {r.get('file', 'Unknown')}\n{r.get('content', '')[:500]}"
                for r in rag_results[:5]
            ])
            
            prompt = f"""You are a code analysis assistant. Answer the following question based on the provided code context and graph information.

Question: {question}

Code Context:
{code_context}

Graph Context:
{graph_context}

Provide a clear, concise answer. Include specific file references when relevant."""
            
            # Query Ollama
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("response", "No response generated")
                else:
                    logger.error(f"Ollama API error: {response.status_code}")
                    return "Failed to generate response"
                    
        except Exception as e:
            logger.error(f"Ollama query failed: {e}")
            return "Failed to generate response"
    
    def _extract_relevant_nodes(self, rag_results: List[dict]) -> List[str]:
        """
        Extract node keys from RAG results.
        
        Args:
            rag_results: RAG search results
        
        Returns:
            List of node keys
        
        Requirements:
            - 6.4: Node highlighting logic
        """
        node_keys = []
        
        for result in rag_results:
            node_key = result.get('node_key') or result.get('namespace_key')
            if node_key and node_key not in node_keys:
                node_keys.append(node_key)
        
        return node_keys
    
    def _extract_references(
        self,
        answer: str,
        rag_results: List[dict]
    ) -> List[CodeReference]:
        """
        Extract code references from answer and RAG results.
        
        Args:
            answer: AI-generated answer
            rag_results: RAG search results
        
        Returns:
            List of code references
        
        Requirements:
            - 6.8: Code reference extraction
        """
        references = []
        
        # Extract file mentions from answer
        file_pattern = r'`([^`]+\.(java|ts|tsx|js|py|sql))`'
        file_matches = re.findall(file_pattern, answer, re.IGNORECASE)
        
        mentioned_files = {match[0] for match in file_matches}
        
        # Match with RAG results
        for result in rag_results[:5]:
            file_path = result.get('file', '')
            
            # Check if this file was mentioned in the answer
            if any(mentioned in file_path for mentioned in mentioned_files):
                references.append(CodeReference(
                    file=file_path,
                    line=result.get('line', 0),
                    snippet=result.get('content', '')[:200],
                    node_key=result.get('node_key', '') or result.get('namespace_key', '')
                ))
        
        return references
    
    def _calculate_confidence(
        self,
        rag_results: List[dict],
        answer: str
    ) -> float:
        """
        Calculate confidence score for the answer.
        
        Based on:
        - Number of relevant documents found
        - Presence of specific references in answer
        
        Args:
            rag_results: RAG search results
            answer: AI-generated answer
        
        Returns:
            Confidence score (0.0 to 1.0)
        
        Requirements:
            - 6.3: Confidence calculation
        """
        confidence = 0.0
        
        # Base confidence on number of RAG results
        if len(rag_results) >= 5:
            confidence += 0.5
        elif len(rag_results) >= 3:
            confidence += 0.3
        elif len(rag_results) >= 1:
            confidence += 0.1
        
        # Boost if answer contains specific references
        if '`' in answer:  # Contains code references
            confidence += 0.2
        
        if any(keyword in answer.lower() for keyword in ['file:', 'class', 'function', 'method']):
            confidence += 0.2
        
        # Penalize if answer is too short
        if len(answer) < 50:
            confidence *= 0.5
        
        return min(1.0, confidence)
