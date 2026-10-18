ProjectIQ
=========

AI-Powered Project and Tender Analysis Platform
-----------------------------------------------

ProjectIQ is an ongoing project designed to streamline project planning and tender analysis through automated document processing, structured data extraction, and locally executed artificial intelligence models. The primary objective is to assist organizations in evaluating tender documentation, extracting project requirements, identifying potential risks, assessing resource availability, and making informed, evidence-backed decisions.

Status and Development Progress
-------------------------------

ProjectIQ is currently under active development. While the backend infrastructure and core analysis services have been implemented, several components—including portions of the frontend, advanced reporting engines, and deployment workflows—remain in progress.

### Component Implementation Status

**ComponentStatus**FastAPI backend foundation

Implemented

Local AI integration using Ollama

Implemented

Document ingestion and processing foundation

In development

Requirement validation

Implemented

Evidence and quotation verification utilities

Implemented

Contradiction detection across extracted facts

Implemented

Equipment options and capacity analysis

Implemented

Workforce gap analysis foundation

Present in the codebase

Financial and scenario analysis

In development

Frontend and backend integration

In development

CSV, DOCX, and PPTX report generation

Planned / Incomplete

Complete end-to-end workflow

In development

Note: Passing unit tests for individual backend components does not imply that every feature is fully integrated into a user-facing workflow.

Platform Vision
---------------

ProjectIQ provides a unified analytical workspace enabling users to perform the following operations:

*   Upload and analyze project and tender documents.
    
*   Extract structured requirements and pertinent factual data.
    
*   Match requirements against available organizational data.
    
*   Identify missing information and compliance discrepancies.
    
*   Detect contradictions across multiple source documents.
    
*   Evaluate workforce capacities and equipment inventories.
    
*   Perform financial cost modeling, scenario analysis, and risk assessments.
    
*   Explore AI-assisted insights anchored by traceable source evidence.
    
*   Generate evaluation documentation for decision-making processes.
    

Architecture and Technology Stack
---------------------------------

The platform utilizes a modern, modular technology stack designed to support local execution and maintain data privacy:

**TechnologyPurposePython**

Backend development

**FastAPI**

Backend API framework

**Ollama**

Local AI model execution

**SQLAlchemy**

Database interaction and ORM

**Pytest**

Automated testing

**TypeScript / React**

Frontend development

**Tailwind CSS**

Frontend styling

Core Design Principles
----------------------

*   **Evidence Traceability:** Critical findings must retain verifiable supporting data references wherever available.
    
*   **Validation Prior to Acceptance:** Extracted data undergoes systematic validation rather than automated assumption.
    
*   **Transparency of Uncertainty:** Missing information is explicitly identified rather than implicitly evaluated as negative or confirmed.
    
*   **Decision Support:** AI-generated outputs serve to augment human evaluation rather than replace professional verification.
    
*   **Incremental Development:** System modules are designed, tested, and integrated iteratively.
    

Repository Structure
--------------------

## Repository Structure

```text
ProjectIQ/
├── backend/
│   ├── app/
│   │   ├── models/              # Database models
│   │   ├── routers/             # FastAPI API routes
│   │   ├── schemas/             # Request and response schemas
│   │   ├── services/
│   │   │   ├── ai/              # Local AI services
│   │   │   ├── analysis/        # Requirement, risk, and resource analysis
│   │   │   ├── export/          # Report export utilities
│   │   │   ├── ingestion/       # Document ingestion and processing
│   │   │   └── verification/    # Validation and evidence verification
│   │   └── utils/               # Shared utility functions
│   ├── tests/                   # Backend automated tests
│   ├── requirements.txt         # Python dependencies
│   └── ...
├── frontend/
│   ├── src/
│   │   ├── api/                 # Backend API clients
│   │   ├── components/          # Reusable UI components
│   │   └── ...
│   └── ...
├── demo-data/                   # Sample project and tender documents
├── docs/                        # Project documentation
├── eval/                        # Evaluation utilities
├── scripts/                     # Setup and development scripts
├── README.md                    # Project overview and setup guide
├── LICENSE                      # Project license
├── docker-compose.yml           # Docker Compose configuration
└── ...
```

**Note:** This tree provides an overview of the repository. Some directories and files may change as development progresses.


Testing Verification
--------------------

Automated test suites verify implemented backend functionality and mitigate regression risks. The current development branch successfully passes the primary test iterations, though certain environment-specific constraints (such as symbolic-link permissions in Windows testing environments) may require specific configurations.

Project Roadmap
---------------

### Phase 1: Backend Foundation

*   Establish FastAPI backend architecture.
    
*   Integrate local AI execution services.
    
*   Implement structured requirement validation protocols.
    
*   Develop quotation verification and contradiction detection utilities.
    
*   Implement equipment analysis logic and establish automated backend testing.
    

### Phase 2: Analysis and Integration

*   Finalize document processing pipelines.
    
*   Integrate requirement matching and gap analysis models.
    
*   Connect analysis services to corresponding API endpoints.
    
*   Enhance evidence traceability across analytical outputs.
    
*   Complete financial modeling and scenario analysis workflows.
    

### Phase 3: Frontend Development

*   Finalize API client integration and document management interfaces.
    
*   Construct the primary project analysis interface.
    
*   Implement risk, cost, and scenario visualization components.
    
*   Integrate source-linked evidence views and error-handling utilities.
    

### Phase 4: Reporting and Deployment

*   Complete CSV, DOCX, and PPTX export functionalities.
    
*   Finalize local setup scripts and configuration documentation.
    
*   Conduct comprehensive testing using representative project documentation.
    

Installation and Getting Started
--------------------------------

### Prerequisites

*   Python 3.10 or a compatible supported version.
    
*   Git.
    
*   Ollama installed locally with a compatible model configured.
    

### 1\. Clone the Repository

Bash

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   git clone https://github.com/asvibes/ProjectIQ.git  cd ProjectIQ   `

### 2\. Configure the Python Environment

Bash

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   cd backend  python -m venv .venv  .\.venv\Scripts\Activate.ps1   `

### 3\. Install Dependencies

Bash

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   python -m pip install -r requirements.txt   `

### 4\. Configure Local AI

Initialize Ollama and pull the required model configuration as detailed in the official Ollama documentation.

Current Limitations
-------------------

*   The platform is under active development and is not yet designated as a production-ready system.
    
*   Certain functional modules and export capabilities remain incomplete.
    
*   AI-generated outputs require human review and validation prior to utilization.
    
*   Analytical accuracy depends directly on the quality of input documentation and model configuration.
    

License
-------

This project is licensed under the MIT License - see the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.
