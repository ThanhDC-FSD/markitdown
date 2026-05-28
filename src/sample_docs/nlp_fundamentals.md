# Natural Language Processing Fundamentals

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
