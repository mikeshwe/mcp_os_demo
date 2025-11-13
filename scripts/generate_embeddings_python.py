#!/usr/bin/env python3
"""
Embedding generation script using Chroma's built-in embeddings
Usage: python3 scripts/generate_embeddings_python.py <text1> <text2> ...
Texts can be provided as base64-encoded strings or plain text
"""

import sys
import json
import base64
import os
import hashlib

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No text provided"}), file=sys.stderr)
        sys.exit(1)
    
    try:
        project_cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".model_cache"))
        os.makedirs(project_cache_dir, exist_ok=True)
        alt_home = os.path.join(project_cache_dir, "home")
        os.makedirs(alt_home, exist_ok=True)
        os.environ["HOME"] = alt_home
        os.environ["HF_HOME"] = os.path.join(project_cache_dir, "hf")
        os.environ["TRANSFORMERS_CACHE"] = os.path.join(project_cache_dir, "transformers")
        os.environ["TORCH_HOME"] = os.path.join(project_cache_dir, "torch")
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = os.path.join(project_cache_dir, "sentence-transformers")
        
        import chromadb
        from chromadb.utils import embedding_functions
        import numpy as np
        
        # Use Chroma's default embedding function (sentence-transformers/all-MiniLM-L6-v2)
        embedding_function = embedding_functions.DefaultEmbeddingFunction()
        
        # Decode base64 texts if needed, otherwise use as-is
        texts = []
        for arg in sys.argv[1:]:
            try:
                # Try to decode as base64 first
                decoded = base64.b64decode(arg).decode('utf-8')
                texts.append(decoded)
            except:
                # If not base64, use as plain text
                texts.append(arg)
        
        TARGET_DIM = 768
        
        def ensure_dim(vec, dim: int = TARGET_DIM):
            if len(vec) == dim:
                return vec
            result = list(vec)
            if not result:
                result = [0.0]
            while len(result) < dim:
                needed = dim - len(result)
                result.extend(result[:needed])
            if len(result) > dim:
                result = result[:dim]
            return result
        
        def fallback_embedding(text: str, dim: int = TARGET_DIM):
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            values = []
            seed = digest
            while len(values) < dim:
                seed = hashlib.sha256(seed + text.encode("utf-8")).digest()
                for byte in seed:
                    values.append((byte / 255.0) * 2 - 1)
                    if len(values) == dim:
                        break
            return values
        
        embeddings_list = []
        try:
            embeddings = embedding_function(texts)
            for emb in embeddings:
                if isinstance(emb, np.ndarray):
                    embeddings_list.append(ensure_dim(emb.tolist()))
                elif hasattr(emb, 'tolist'):
                    embeddings_list.append(ensure_dim(emb.tolist()))
                else:
                    embeddings_list.append(ensure_dim(list(emb)))
        except Exception as embed_error:
            print(json.dumps({"warning": f"Falling back to deterministic embeddings: {embed_error}"}), file=sys.stderr)
            embeddings_list = [fallback_embedding(text) for text in texts]
        
        # Output as JSON array of arrays (only to stdout)
        print(json.dumps(embeddings_list))
        sys.stdout.flush()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
