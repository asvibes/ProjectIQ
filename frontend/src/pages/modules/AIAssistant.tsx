import { useState, type ChangeEvent, type FormEvent } from 'react';
import {
  Bot,
  FileText,
  Info,
  MessageCircleQuestion,
  Paperclip,
  Send,
  Sparkles,
} from 'lucide-react';
import {
  ApiNotice,
  Button,
  EmptyState,
  Field,
  InlineNotice,
  Panel,
  PageHeader,
  SelectInput,
  StatusPill,
  TextArea,
} from '../../components/common/ui';
import { useApiNotice } from '../../hooks/useApiNotice';

type AssistantScope = 'project' | 'documents' | 'combined';

const suggestedPrompts = [
  'What should we verify before making a decision?',
  'Which evidence is still missing?',
  'Summarise the key delivery constraints.',
];

const scopeOptions: Array<{ value: AssistantScope; label: string }> = [
  { value: 'project', label: 'Current project' },
  { value: 'documents', label: 'Project documents' },
  { value: 'combined', label: 'Project and documents' },
];

export default function AIAssistant() {
  const [scope, setScope] = useState<AssistantScope>('project');
  const [question, setQuestion] = useState('');
  const [submittedQuestion, setSubmittedQuestion] = useState('');
  const { message, clearMessage, reportUnavailable } = useApiNotice();

  const handleScopeChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setScope(event.target.value as AssistantScope);
    clearMessage();
  };

  const handleSuggestion = (prompt: string) => {
    setQuestion(prompt);
    clearMessage();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      reportUnavailable('sending this assistant question');
      return;
    }

    setSubmittedQuestion(trimmedQuestion);
    reportUnavailable('sending this assistant question');
  };

  return (
    <>
      <PageHeader
        eyebrow="Intelligence & outputs / Evidence-grounded assistant"
        title="AI Assistant"
        description="Prepare a question against project evidence, keep its scope explicit, and review source locations when a model and documents are connected."
        actions={<StatusPill tone="amber">Not connected</StatusPill>}
      />

      <div className="content-section stack">
        <ApiNotice />

        <InlineNotice variant="warning">
          <strong>No model or documents are connected.</strong>
          <p>Assistant questions cannot be sent, answered, or cited in this frontend-only workspace.</p>
        </InlineNotice>

        <Panel
          eyebrow="Connection state"
          title="Evidence grounding is waiting for a connection"
          description="The controls below are ready for a future model and document service. They do not load records or send requests."
          action={<StatusPill tone="red">Model unavailable</StatusPill>}
        >
          <div className="panel-body">
            <div className="key-value-list" aria-label="Assistant connection status">
              <div className="key-value-row">
                <span>Model connection</span>
                <strong>Not connected</strong>
              </div>
              <div className="key-value-row">
                <span>Project context</span>
                <strong>Not loaded</strong>
              </div>
              <div className="key-value-row">
                <span>Document evidence</span>
                <strong>None connected</strong>
              </div>
              <div className="key-value-row">
                <span>Answer and citations</span>
                <strong>Unavailable</strong>
              </div>
            </div>
            <div className="dashboard-disclaimer">
              <Info size={16} strokeWidth={1.8} aria-hidden="true" />
              <p><strong>Nothing is inferred from this empty state.</strong> Missing documents remain unknown rather than becoming evidence of a gap or a conclusion.</p>
            </div>
          </div>
        </Panel>

        <div className="split-grid">
          <Panel
            eyebrow="Question setup"
            title="Ask about the evidence"
            description="Choose a scope and write a question. Your draft stays on this screen until you change it."
          >
            <form className="panel-body" onSubmit={handleSubmit}>
              <Field
                label="Project and document scope"
                htmlFor="assistant-scope"
                hint="Scope selection is local only; no project or document records are currently available."
              >
                <SelectInput id="assistant-scope" value={scope} onChange={handleScopeChange}>
                  {scopeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </SelectInput>
              </Field>

              <div className="dashboard-disclaimer">
                <FileText size={16} strokeWidth={1.8} aria-hidden="true" />
                <p><strong>{scopeOptions.find((option) => option.value === scope)?.label}</strong> is selected, but its connected evidence is not available.</p>
              </div>

              <Field
                className="field-full"
                label="Question"
                htmlFor="assistant-question"
                hint="Questions remain local when the assistant is unavailable."
              >
                <TextArea
                  id="assistant-question"
                  value={question}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => { setQuestion(event.target.value); clearMessage(); }}
                  placeholder="Ask a question about the connected project evidence"
                  rows={5}
                  required
                  maxLength={2000}
                />
              </Field>

              <div className="form-actions form-actions-left">
                <Button type="submit" variant="primary" icon={Send}>Send question</Button>
                <span className="field-hint">No request will be made while disconnected.</span>
              </div>
              {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}
            </form>
          </Panel>

          <Panel
            eyebrow="Suggested prompts"
            title="Start with a review question"
            description="These prompts are starting points only. Selecting one places it in the question field; it does not submit anything."
          >
            <div className="panel-body">
              <div className="filter-row" role="list" aria-label="Suggested assistant prompts">
                {suggestedPrompts.map((prompt) => (
                  <button
                    className={`filter-chip${question === prompt ? ' is-active' : ''}`}
                    key={prompt}
                    type="button"
                    role="listitem"
                    aria-pressed={question === prompt}
                    onClick={() => handleSuggestion(prompt)}
                  >
                    <Sparkles size={14} strokeWidth={1.8} aria-hidden="true" />
                    {prompt}
                  </button>
                ))}
              </div>
              <div className="assistant-scope-note">
                <Paperclip size={16} strokeWidth={1.8} aria-hidden="true" />
                <p><strong>Grounding rule:</strong> a connected answer must point back to a document location. No source chip is available until evidence is connected.</p>
              </div>
            </div>
          </Panel>
        </div>

        <Panel
          eyebrow="Conversation"
          title="Question history"
          description="Only local question drafts are shown here. The assistant will never generate an answer or citation without a connected model and document evidence."
          action={<StatusPill tone="neutral">No live conversation</StatusPill>}
        >
          <div className="panel-body">
            {!submittedQuestion ? (
              <EmptyState
                icon={MessageCircleQuestion}
                title="No question sent"
                description="Write a question above to keep a local draft. Sending remains unavailable while the model and documents are disconnected."
              />
            ) : (
              <div className="assistant-turn" aria-live="polite">
                <div className="assistant-message assistant-message-user">
                  <div className="assistant-message-meta">
                    <MessageCircleQuestion size={16} strokeWidth={1.8} aria-hidden="true" />
                    <strong>Your question</strong>
                    <StatusPill tone="amber">Not sent</StatusPill>
                  </div>
                  <p>{submittedQuestion}</p>
                </div>
                <div className="assistant-source-slot" aria-label="Source chip location">
                  <span className="field-hint">Source location</span>
                  <span className="source-chip source-chip-empty"><Paperclip size={13} strokeWidth={1.8} aria-hidden="true" />No source available</span>
                </div>
                <InlineNotice variant="warning">
                  <strong>Nothing was sent.</strong> No model is connected, so no answer or citation was generated. Your question remains in the input above.
                </InlineNotice>
              </div>
            )}
          </div>
        </Panel>

        <div className="dashboard-disclaimer">
          <Bot size={16} strokeWidth={1.8} aria-hidden="true" />
          <p><strong>Decision support only.</strong> When connected, review each answer against its quoted source and keep consequential decisions with qualified people.</p>
        </div>
      </div>
    </>
  );
}
