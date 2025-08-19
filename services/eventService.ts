// services/eventService.ts

// Define all event types
export type EventType = 
  | 'visualization-ready' 
  | 'thought-completion' 
  | 'thought-stream-complete';

// Define event detail types
export interface VisualizationEventDetail {
  chartData: any;
  chartTitle?: string;
}

export interface ThoughtCompletionEventDetail {
  type: 'answer' | 'result';
  content: string;
  sessionId: string;
}

export interface ThoughtStreamCompleteDetail {
  sessionId: string;
  finalAnswer?: string;
}

// Type-safe event dispatch
export const dispatchEvent = {
  visualizationReady: (detail: VisualizationEventDetail) => {
    const event = new CustomEvent('visualization-ready', { detail });
    window.dispatchEvent(event);
    return event;
  },
  
  thoughtCompletion: (detail: ThoughtCompletionEventDetail) => {
    const event = new CustomEvent('thought-completion', { detail });
    window.dispatchEvent(event);
    return event;
  },
  
  thoughtStreamComplete: (detail: ThoughtStreamCompleteDetail) => {
    const event = new CustomEvent('thought-stream-complete', { detail });
    window.dispatchEvent(event);
    return event;
  }
};

// Type-safe event subscription
export const subscribeToEvent = {
  visualizationReady: (handler: (detail: VisualizationEventDetail) => void) => {
    const eventHandler = ((e: CustomEvent) => handler(e.detail)) as EventListener;
    window.addEventListener('visualization-ready', eventHandler);
    return () => window.removeEventListener('visualization-ready', eventHandler);
  },
  
  thoughtCompletion: (handler: (detail: ThoughtCompletionEventDetail) => void) => {
    const eventHandler = ((e: CustomEvent) => handler(e.detail)) as EventListener;
    window.addEventListener('thought-completion', eventHandler);
    return () => window.removeEventListener('thought-completion', eventHandler);
  },
  
  thoughtStreamComplete: (handler: (detail: ThoughtStreamCompleteDetail) => void) => {
    const eventHandler = ((e: CustomEvent) => handler(e.detail)) as EventListener;
    window.addEventListener('thought-stream-complete', eventHandler);
    return () => window.removeEventListener('thought-stream-complete', eventHandler);
  }
};