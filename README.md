# Confluence → SharePoint Sync (Copilot Studio)

## Overview
This repository contains an automated synchronization service that mirrors selected documentation from **Confluence Cloud** into **SharePoint**.  
SharePoint is then used as the **knowledge source for an AI agent built in Copilot Studio**.

The goal is to ensure that the AI agent always has access to up-to-date, structured, and curated documentation — without any manual work.

## What the service does
- Fetches pages and attachments from configured Confluence spaces
- Mirrors the Confluence hierarchy exactly in SharePoint
- Exports Confluence pages as HTML
- Filters out non-relevant or unsafe attachments (e.g. images, archives, certificates)
- Syncs:
  - new documents
  - updated documents
  - (during reconciliation) deleted or moved documents
- Runs automatically as a scheduled job on a server