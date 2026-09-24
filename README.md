# Confluence → SharePoint Data Pipeline for RAG

## Overview

This repository implements an automated data pipeline for preparing and synchronizing enterprise documentation for a **production-grade Retrieval-Augmented Generation (RAG) system**.

The service continuously ingests documentation from **Confluence Cloud**, processes and structures the content, and synchronizes it to **SharePoint**, where it can be used as a curated knowledge source for an AI agent.

The goal is to maintain a reliable, up-to-date knowledge base for retrieval without requiring manual data preparation.

## What the service does

- Ingests pages and attachments from configured Confluence spaces
- Preserves the original documentation hierarchy in SharePoint
- Converts Confluence pages into retrieval-ready HTML documents
- Filters unsupported or unnecessary attachments
- Detects and synchronizes new and updated content
- Reconciles deleted or moved documents
- Maintains synchronization state between runs
- Runs automatically as a scheduled production service

## Architecture

**Confluence Cloud → Data Processing & Sync Pipeline → SharePoint → RAG / AI Agent**

The pipeline handles the ingestion and preparation layer of the RAG system, ensuring that the downstream AI application operates on current and consistently structured documentation.
