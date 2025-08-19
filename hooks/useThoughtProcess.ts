import { useState, useEffect, useCallback, useRef } from 'react';
import { dispatchEvent, subscribeToEvent } from '@/services/eventService';

// Define ChartData interface
interface ChartData {
  chartType: string;
  config: {
    title?: string;
    description?: string;
    trend?: {
      percentage?: number;
      direction?: 'up' | 'down';
    };
    footer?: string;
    totalLabel?: string;
    xAxisKey?: string;
  };
  data: any[];
  chartConfig: Record<string, {
    label?: string;
    color?: string;
    stacked?: boolean;
  }>;
}

interface Thought {
  type: string;
  content: string;
  timestamp?: string;
  node?: string;
  from_router?: boolean;
  id: string;
  category?: 'setup' | 'analysis' | 'tool' | 'result' | 'error' | 'visualization_data' | 'user_input';
  technical_details?: Record<string, any>;
  visualization?: {
    chart_data: ChartData;
    chart_type: string;
    chart_title?: string;
  };
}

interface PartialThought {
  type: string;
  content: string;
  timestamp?: string;
  node?: string;
  from_router?: boolean;
  id?: string; 
  category?: 'setup' | 'analysis' | 'tool' | 'result' | 'error' | 'visualization_data' | 'user_input';
  technical_details?: Record<string, any>;
  visualization?: {
    chart_data: ChartData;
    chart_type: string;
    chart_title?: string;
  };
}

interface ThoughtEventData {
  type: string;
  content?: string;
  message?: string;
  category?: 'setup' | 'analysis' | 'tool' | 'result' | 'error' | 'visualization_data' | 'user_input';
  node?: string;
  timestamp?: string;
  technical_details?: Record<string, any>;
  visualization?: {
    chart_data: ChartData;
    chart_type: string;
    chart_title?: string;
  };
}

export function useThoughtProcess(sessionId?: string) {
  const [thoughts, setThoughts] = useState<Thought[]>([]);
  const [connected, setConnected] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState<boolean>(false);
  const [visualization, setVisualization] = useState<ChartData | null>(null);
  const [requestTimestamp, setRequestTimestamp] = useState<number>(0);
  const eventSourceRef = useRef<EventSource | null>(null);
  const previousSessionRef = useRef<string | undefined>(undefined);

  const generateId = useCallback((prefix: string = 'thought') => {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).substring(2, 15)}`;
  }, []);

  const updateThoughts = useCallback((newThought: PartialThought) => {
    const thoughtWithId = {
      ...newThought,
      id: newThought.id || generateId('thought')
    } as Thought;
    
    setThoughts(prevThoughts => [...prevThoughts, thoughtWithId]);
  }, [generateId]);
  
  const normalizeThoughtData = useCallback((data: ThoughtEventData): Thought => {
    const currentTimestamp = data.timestamp || new Date().toISOString();
    
    if (data.type === 'thought') {
      return {
        ...data,
        id: generateId('thought'),
        type: 'reasoning',
        category: data.category || 'analysis',
        node: data.node || undefined,
        content: data.content || '',
        timestamp: currentTimestamp,
        technical_details: data.technical_details
      } as Thought;
    } 
    if (data.type === 'question') {
      return {
        ...data,
        id: generateId('user-question'),
        type: 'question',
        node: data.node || 'User',
        category: 'user_input',
        content: data.content || '',
        timestamp: currentTimestamp
      } as Thought;
    }  
    
    return {
      ...data,
      id: generateId('thought'),
      type: data.type === 'thinking' || data.type === 'tool_result' ? 'reasoning' : data.type,
      node: data.node || undefined,
      content: data.content || '',
      timestamp: currentTimestamp
    } as Thought;
  }, [generateId]);

  const handleEventData = useCallback((data: any) => {
    try {
      if (data.type === 'connected') {
        setConnected(true);
        setError(null);
      } else if (data.type === 'error') {
        setError(data.message);
      } else if (data.type === 'complete') {
        setIsComplete(true);
      } else if (['thought', 'rationale', 'reasoning', 'thinking', 'tool_result', 'question'].includes(data.type)) {
        const normalizedThought = normalizeThoughtData(data);  
        if (data.category === 'visualization_data' && data.visualization) {
          setVisualization(data.visualization.chart_data);
  
          const chartData = data.visualization.chart_data;
          if (chartData && chartData.chartType && chartData.data && Array.isArray(chartData.data)) {
            dispatchEvent.visualizationReady({
              chartData: chartData,
              chartTitle: data.visualization.chart_title
            });
            
            if (sessionId) {
              dispatchEvent.thoughtCompletion({
                type: 'result',
                content: `Visualization generated: ${data.visualization.chart_title || 'Chart'}`,
                sessionId: sessionId
              });
            }
          }
        }
        
        updateThoughts(normalizedThought);
      }
    } catch (err) {
      console.error(`Error processing event data:`, err);
    }
  }, [updateThoughts, normalizeThoughtData]);

  const setupEventSource = useCallback((sessionId: string) => {
    if (!sessionId) return null;
    
    const sseUrl = `/api/financial/thoughts/${sessionId}`;
    
    try {
      const eventSource = new EventSource(sseUrl, { withCredentials: false });
      
      eventSource.onopen = () => {
        setConnected(true);
        setError(null);
      };
      
      eventSource.onerror = () => {
        if (eventSource.readyState === EventSource.CLOSED) {
          setConnected(false);
          setError('Connection to thought process stream failed');
        }
      };
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleEventData(data);
        } catch (err) {
          console.error(`Error processing SSE message:`, err);
        }
      };
      
      return eventSource;
    } catch (error) {
      console.error(`Error setting up EventSource:`, error);
      setError('Failed to establish connection');
      return null;
    }
  }, [handleEventData]);

  useEffect(() => {
    // Create new EventSource when sessionId changes
    if (sessionId && sessionId !== previousSessionRef.current) {
      // Close previous connection if exists
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      
      setThoughts([]);
      setError(null);
      setIsComplete(false);
      
      const newEventSource = setupEventSource(sessionId);
      if (newEventSource) {
        eventSourceRef.current = newEventSource;
        previousSessionRef.current = sessionId;
      }
    }
    
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [sessionId, setupEventSource]);

  useEffect(() => {
    if (thoughts.length > 0) {
      const lastThought = thoughts[thoughts.length - 1];
      
      // Check if this is a result or visualization response
      if ((lastThought.category === 'result' && lastThought.node === 'Answer') ||
          (lastThought.category === 'visualization_data' && lastThought.node === 'Visualization')) {
        if (sessionId) {
          // Use the shared event service
          dispatchEvent.thoughtCompletion({
            type: 'answer',
            content: lastThought.content,
            sessionId: sessionId
          });
          setIsComplete(true);
        }
      }
    }
  }, [thoughts, sessionId]);

  return { 
    thoughts, 
    connected, 
    error, 
    isComplete,
    visualization
  };
}

export default useThoughtProcess;