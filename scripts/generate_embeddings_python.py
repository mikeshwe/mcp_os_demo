#!/usr/bin/env python3
"""
Embedding generation script using Chroma's built-in embeddings
Usage: python3 scripts/generate_embeddings_python.py <text1> <text2> ...
Texts can be provided as base64-encoded strings or plain text
"""

import sys
import json
import base64

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No text provided"}), file=sys.stderr)
        sys.exit(1)
    
    try:
        import chromadb
        from chromadb.utils import embedding_functions
        
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
        
        embeddings = embedding_function(texts)
        
        # Convert numpy arrays to lists for JSON serialization
        embeddings_list = []
        import numpy as np
        for emb in embeddings:
            if isinstance(emb, np.ndarray):
                embeddings_list.append(emb.tolist())
            elif hasattr(emb, 'tolist'):
                embeddings_list.append(emb.tolist())
            else:
                embeddings_list.append(list(emb))
        
        # Output as JSON array of arrays (only to stdout)
        print(json.dumps(embeddings_list))
        sys.stdout.flush()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
