"""Simple crawler to fetch sample documents for knowledge base population."""

import os
import json
from pathlib import Path
from typing import List
import requests


def fetch_from_urls(urls: List[str], output_dir: str = "./sample_docs") -> None:
    """
    Fetch HTML documents from URLs and save them.

    Args:
        urls: List of URLs to fetch
        output_dir: Directory to save downloaded files
    """
    os.makedirs(output_dir, exist_ok=True)

    for idx, url in enumerate(urls):
        try:
            print(f"Fetching: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Generate filename
            filename = f"doc_{idx}.html"
            filepath = os.path.join(output_dir, filename)

            # Save content
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(response.text)

            print(f"Saved: {filepath}")

        except Exception as e:
            print(f"Error fetching {url}: {e}")


def create_sample_documents(output_dir: str = "./sample_docs") -> None:
    """
    Create sample markdown documents for testing.

    Args:
        output_dir: Directory to save sample documents
    """
    os.makedirs(output_dir, exist_ok=True)

    # Sample documents about machine learning
    samples = {
        "machine_learning_basics.md": """# Machine Learning Basics

## What is Machine Learning?

Machine learning (ML) is a subset of artificial intelligence (AI) that focuses on the development of computer systems that can learn and improve from experience without being explicitly programmed.

## Types of Machine Learning

### Supervised Learning
Supervised learning involves training data with labeled examples. The algorithm learns to map inputs to outputs.
- Classification: Predicting categories (e.g., spam/not spam)
- Regression: Predicting continuous values (e.g., house prices)

### Unsupervised Learning
Unsupervised learning finds patterns in unlabeled data.
- Clustering: Grouping similar items
- Dimensionality Reduction: Reducing features

### Reinforcement Learning
Reinforcement learning trains agents to make sequences of decisions.
- Agent learns by interacting with an environment
- Receives rewards for good actions, penalties for bad ones

## Common Algorithms

### Linear Regression
A simple supervised learning algorithm for predicting continuous values.

### Decision Trees
Hierarchical models that split data based on features.

### Neural Networks
Inspired by biological neurons, with interconnected layers of nodes.

### Support Vector Machines (SVM)
Finds optimal hyperplanes to separate classes.

## Machine Learning Workflow

1. Data Collection: Gather relevant data
2. Data Preprocessing: Clean and prepare data
3. Feature Engineering: Select and create features
4. Model Selection: Choose appropriate algorithm
5. Training: Fit model to training data
6. Evaluation: Assess performance on test data
7. Hyperparameter Tuning: Optimize model parameters
8. Deployment: Use model for predictions
""",
        "deep_learning_guide.md": """# Deep Learning Guide

## Introduction to Deep Learning

Deep learning is a subset of machine learning that uses artificial neural networks with multiple layers (deep neural networks) to learn representations of data.

## Neural Network Architecture

### Input Layer
Receives the raw features from the input data.

### Hidden Layers
Perform feature extraction and transformation through learned weights.

### Output Layer
Produces the final predictions.

## Types of Neural Networks

### Convolutional Neural Networks (CNN)
Specialized for image and spatial data processing.
- Use convolutional filters to extract features
- Effective for image classification and object detection

### Recurrent Neural Networks (RNN)
Designed for sequential data with temporal dependencies.
- LSTM (Long Short-Term Memory): Improved RNN with memory cells
- GRU (Gated Recurrent Unit): Simplified version of LSTM

### Transformers
State-of-the-art architecture for NLP tasks.
- Self-attention mechanism
- Parallel processing of sequences
- Foundation for models like BERT and GPT

## Training Deep Neural Networks

### Backpropagation
Algorithm for computing gradients and updating weights.

### Gradient Descent
Optimization technique to minimize loss function.
- Stochastic Gradient Descent (SGD)
- Adam Optimizer
- RMSprop

### Regularization Techniques
Prevent overfitting:
- Dropout: Randomly deactivate neurons
- L1/L2 Regularization: Penalize large weights
- Batch Normalization: Normalize layer inputs

## Common Applications

- Image Recognition: Classifying images into categories
- Natural Language Processing: Text analysis and generation
- Speech Recognition: Converting audio to text
- Recommendation Systems: Suggesting items to users
- Autonomous Vehicles: Perception and decision making
""",
        "nlp_fundamentals.md": """# Natural Language Processing Fundamentals

## What is NLP?

Natural Language Processing (NLP) is a field of artificial intelligence that focuses on enabling computers to understand and generate human language.

## Core NLP Tasks

### Text Classification
Categorizing text into predefined classes.
- Sentiment Analysis: Determining positive/negative sentiment
- Topic Classification: Assigning topics to documents
- Intent Detection: Understanding user intent from text

### Named Entity Recognition (NER)
Identifying and extracting entities from text.
- Person names, organization names, locations
- Temporal expressions, quantities

### Machine Translation
Converting text from one language to another.
- Statistical approaches
- Neural approaches with seq2seq models

### Question Answering
Systems that answer questions based on context.
- Extractive QA: Finding answer spans in text
- Generative QA: Generating answers

## Text Preprocessing

### Tokenization
Splitting text into individual tokens (words, subwords).
- Word tokenization
- Subword tokenization (BPE, WordPiece)

### Normalization
Standardizing text:
- Lowercasing
- Removing punctuation
- Stemming and lemmatization

### Stop Word Removal
Removing common words that don't add meaning.

## Word Representations

### Bag of Words
Simple representation counting word occurrences.

### TF-IDF
Term Frequency-Inverse Document Frequency weighing.

### Word Embeddings
Dense vector representations:
- Word2Vec: Captures semantic meaning
- GloVe: Global vectors for word representation
- FastText: Subword information

## Advanced NLP Models

### Language Models
Predict next word given context.
- N-gram models
- Neural language models
- Transformer-based models (GPT, BERT)

### Attention Mechanism
Allows model to focus on relevant parts of input.
- Self-attention
- Cross-attention

### Sequence-to-Sequence Models
Encode input sequence, decode output sequence.
- Machine translation
- Summarization
- Question answering
""",
    }

    for filename, content in samples.items():
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Created: {filepath}")


def main():
    """Main crawler function."""
    import argparse

    parser = argparse.ArgumentParser(description="Fetch sample documents for RAG KB")
    parser.add_argument(
        "--mode",
        choices=["sample", "urls"],
        default="sample",
        help="Fetch mode: 'sample' creates local docs, 'urls' fetches from URLs",
    )
    parser.add_argument(
        "--output",
        default="./sample_docs",
        help="Output directory for documents",
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        default=[
            "https://en.wikipedia.org/wiki/Machine_learning",
            "https://en.wikipedia.org/wiki/Deep_learning",
            "https://en.wikipedia.org/wiki/Natural_language_processing",
        ],
        help="URLs to fetch (for --mode urls)",
    )

    args = parser.parse_args()

    if args.mode == "sample":
        print("Creating sample documents...")
        create_sample_documents(args.output)
    else:
        print(f"Fetching documents from URLs...")
        fetch_from_urls(args.urls, args.output)

    print(f"Documents saved to: {args.output}")


if __name__ == "__main__":
    main()
