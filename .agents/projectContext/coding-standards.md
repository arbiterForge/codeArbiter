<!--PLACEHOLDER-->
<!-- Populated by decompose/context-creation skill. -->

# Coding Standards

## Naming Conventions

_Variable, function, class, file naming rules._

## Formatting

_Indentation, line length, trailing commas, semicolons, etc._

## Import Style

_Import ordering, relative vs. absolute paths, etc._

## Type Safety

_Type annotation requirements, banned patterns (e.g., no `any`)_

## Banned Patterns

_Specific code patterns that are banned (e.g., `eval`, `shell: true`, raw SQL)_

## File Organization

_How files should be organized within the project_

## Test Conventions

_Test file location, naming, structure requirements_

## Comment Style

_When to comment, how to comment, what NOT to comment_

## File Header Requirements

_Copyright holder (individual name, team, company, or username — whatever is legally appropriate
for this project):_

Required fields in the first comment block of every new file:
- Copyright: `Copyright (c) <YEAR> <COPYRIGHT_HOLDER>`
- Author: individual or team name
- Created: ISO date (YYYY-MM-DD) or year of first creation
- File: the file's own name (aids traceability after copy/rename)
- Language/syntax: include when not obvious from file extension

Revision note policy:
- For significant additions (new feature, new component, new service): add a one-line inline note
  near the change (e.g., `<!-- CHANGES: added redis pod deployment 2026-05-13 -->`)
- Minor changes (formatting, typo fixes) do not require revision notes
