# Relay Frontend Home Design

## What this feature is

Relay needs a polished public home page that explains the product quickly and makes its reliability story memorable. The page will turn the existing design reference into a production-ready React experience with a clearer hierarchy, stronger visual identity, and better responsive behavior.

## Why it matters

The home page is the first product experience for a new visitor. It should communicate that Relay is a serious self-hosted job platform, make its core correctness guarantees understandable, and give users a clear path into the operator console or documentation.

## Who uses it

- Engineers evaluating Relay for background job processing.
- Operators who want to understand Relay's reliability and observability model.
- Existing users returning to the console or documentation.

## User workflow

A visitor lands on the page, understands the product promise, sees a credible preview of live operations, reviews the system's main strengths, and chooses to open the console or learn how Relay works.

## Included

- A responsive public Home page in the existing frontend application.
- Clear navigation and primary calls to action.
- A high-impact hero focused on Relay's durability promise.
- A visual operations preview that reflects Relay concepts such as queues, workers, throughput, and job state.
- Accessible interaction and readable layouts across desktop and mobile screens.
- Styling built with the existing React and CSS toolchain.

## Out of scope

- Authentication implementation.
- Live API or WebSocket data.
- Operator dashboard pages such as Jobs, Queues, Workers, or DLQ.
- Backend changes.
- A new UI framework or design-system dependency.

## How users know it works

The root page loads without errors, clearly identifies Relay and its value, provides visible console and product-information actions, and remains usable and visually coherent at desktop and mobile widths.
