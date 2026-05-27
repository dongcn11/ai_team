# Acceptance Criteria

## Feature: Khởi tạo dự án

### Story 1: Create a new project
- **Given** I am on the dashboard page
- **When** I click the "Create New Project" button
- **Then** I should be redirected to the project creation form

### Story 2: Specify project name and description
- **Given** I am on the project creation form
- **When** I enter a project name and description
- **Then** I should be able to save the project with the provided information
- **And** the project name should be required and unique

### Story 3: Select project template
- **Given** I am on the project creation form
- **When** I select a template from the dropdown
- **Then** the project should be initialized with the predefined structure of that template

### Story 4: Configure project settings
- **Given** I am on the project creation form
- **When** I configure the initial settings (language, voice, format)
- **Then** the project should be saved with those settings applied

### Story 5: Confirmation after project creation
- **Given** I have filled out all required fields in the project creation form
- **When** I click the "Create Project" button
- **Then** I should see a success notification
- **And** I should be redirected to the newly created project page
