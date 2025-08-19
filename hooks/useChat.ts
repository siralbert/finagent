import { useState, useCallback, useRef, useEffect } from 'react';
import { apiRequest } from '@/utils/api';
import { toast } from "@/hooks/use-toast";
import { readFileAsText, readFileAsBase64, readFileAsPDFText } from "@/utils/fileHandling";
import type { Message, FileUpload, AnalyzeAPIResponse, APIResponse } from '@/types/chat';
import { subscribeToEvent } from '@/services/eventService';
import {
  prepareApiMessages,
  createUserMessage,
  createAssistantTextMessage,
  createErrorMessage,
  createVisualizationMessage
} from '@/utils/messageUtils';

interface ChatState {
  messages: Message[];
  input: string;
  isLoading: boolean;
  isThinking: boolean;
  currentUpload: FileUpload | null;
  isUploading: boolean;
  queryDetails: AnalyzeAPIResponse[];
  sessionId?: string;
}

interface ChatActions {
  setInput: (input: string) => void;
  handleSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  handleInputChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  handleReset: () => void;
  setCurrentUpload: (upload: FileUpload | null) => void;
}

export interface UseChatReturn extends ChatState {
  actions: ChatActions;
  fileInputRef: React.RefObject<HTMLInputElement>;
}

type ApiResponseHandler = ({
  apiMessages,
  responseData,
  setterFunctions,
}: {
  apiMessages: any[];
  responseData: any;
  setterFunctions: {
    setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
    setQueryDetails: React.Dispatch<React.SetStateAction<AnalyzeAPIResponse[]>>;
    setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
    setIsThinking: React.Dispatch<React.SetStateAction<boolean>>;
    setCurrentUpload: React.Dispatch<React.SetStateAction<FileUpload | null>>;
    setSessionId?: React.Dispatch<React.SetStateAction<string | undefined>>;
    originalQuestion: string;
    selectedModel: string;
    selectedRegion: string;
  };
}) => Promise<{
  analyzeTime?: number;
  visualizeTime?: number;
}>;

export const useChat = (selectedModel: string, selectedRegion: string): UseChatReturn => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [currentUpload, setCurrentUpload] = useState<FileUpload | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [queryDetails, setQueryDetails] = useState<AnalyzeAPIResponse[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isSubmitting = useRef(false);
  const thinkingStartTime = useRef<number | null>(null);
  
  useEffect(() => {
    const validateAndLoadSession = async () => {
      if (typeof window !== 'undefined') {
        const savedSessionId = window.localStorage.getItem('session_id');
        if (savedSessionId) {
          try {
            console.log(`Validating saved session ID: ${savedSessionId}`);
            const response = await apiRequest(`router/validate-session/${savedSessionId}`, {
              method: 'GET',
              headers: { 
                'Content-Type': 'application/json' 
              },
            });
            
            if (response.ok) {
              const data = await response.json();
              
              if (data.valid) {
                console.log(`Session ${savedSessionId} is valid, reusing`);
                setSessionId(savedSessionId);
              } else {
                console.log(`Session ${savedSessionId} is invalid, removing from storage`);
                window.localStorage.removeItem('session_id');
              }
            } else {
              console.warn(`Session validation failed with status: ${response.status}`);
              window.localStorage.removeItem('session_id');
            }
          } catch (error) {
            console.error("Failed to validate session:", error);
            window.localStorage.removeItem('session_id');
          }
        }
      }
    };
    
    validateAndLoadSession();
  }, [selectedRegion]);
  
  // Effect to track thinking start time
  useEffect(() => {
    if (isThinking) {
      thinkingStartTime.current = Date.now();
    }
  }, [isThinking]);
  
  const getProcessingTime = () => {
    if (thinkingStartTime.current) {
      const processingTimeMs = Date.now() - thinkingStartTime.current;
      const processingTimeSec = (processingTimeMs / 1000).toFixed(2);
      return processingTimeSec;
    }
    return null;
  };
  
  useEffect(() => {
    // Handle visualization events with the shared event service
    const unsubscribeVisualization = subscribeToEvent.visualizationReady(({ chartData, chartTitle }) => {
      if (chartData) {
        const processingTime = getProcessingTime();
        setMessages(prev => [
          ...prev,
          createVisualizationMessage(
            `Here's the visualization based on the data:${processingTime ? ` (Generated in ${processingTime}s)` : ''}`, 
            { 
              chart_data: chartData, 
              chart_type: chartData.chartType,
              chart_title: chartTitle || chartData.config?.title
            },
            new Date().toISOString() // Add timestamp for visualization message
          )
        ]);
        setIsThinking(false);
        thinkingStartTime.current = null;
      }
    });
    
    // Handle thought completion events with the shared event service
    const unsubscribeThoughtCompletion = subscribeToEvent.thoughtCompletion(({ type, content, sessionId: eventSessionId }) => {
      if (
        (type === 'answer' || type === 'result') && 
        eventSessionId === sessionId &&
        content
      ) {
        const processingTime = getProcessingTime();
        const updatedContent = processingTime 
          ? `${content}\n\n_Processing time: ${processingTime}s_` 
          : content;
          
        setMessages(prev => [
          ...prev,
          createAssistantTextMessage(updatedContent, new Date().toISOString()) // Add timestamp for assistant message
        ]);
        
        setIsThinking(false);
        thinkingStartTime.current = null;
      }
    });
  
    // Handle thought stream completion events with the shared event service
    const unsubscribeThoughtStreamComplete = subscribeToEvent.thoughtStreamComplete(({ sessionId: eventSessionId, finalAnswer }) => {
      if (eventSessionId === sessionId) {
        console.log("Thought stream complete for session:", eventSessionId);
        
        if (finalAnswer) {
          const processingTime = getProcessingTime();
          const updatedAnswer = processingTime 
            ? `${finalAnswer}\n\n_Processing time: ${processingTime}s_` 
            : finalAnswer;
            
          setMessages(prev => [
            ...prev,
            createAssistantTextMessage(updatedAnswer, new Date().toISOString()) // Add timestamp for assistant message
          ]);
        }
        
        setIsThinking(false);
        thinkingStartTime.current = null;
      }
    });
    
    // Return cleanup function to unsubscribe from all events
    return () => {
      unsubscribeVisualization();
      unsubscribeThoughtCompletion();
      unsubscribeThoughtStreamComplete();
    };
  }, [sessionId]);  
  
  const responseHandlers: Record<string, ApiResponseHandler> = {
    'financial': async ({ apiMessages, responseData, setterFunctions }) => {
      const { setSessionId } = setterFunctions;
      const responseSessionId = responseData.input?.session_id;
      const directAnswer = responseData.input?.direct_answer;

      if (responseSessionId) {
        setSessionId(responseSessionId);
      } else {
        console.warn('Missing sessionId in response');
      }
      
      // Handle immediate answers
      if (directAnswer && directAnswer !== "processing") {
        const processingTime = getProcessingTime();
        const updatedAnswer = processingTime 
          ? `${directAnswer}\n\n_Processing time: ${processingTime}s_` 
          : directAnswer;
          
        console.log("Adding immediate answer to messages:", updatedAnswer);
        setMessages(prev => [
          ...prev,
          createAssistantTextMessage(updatedAnswer, new Date().toISOString()) // Add timestamp for assistant message
        ]);
        setIsThinking(false);
        thinkingStartTime.current = null;
      }
    
      return { analyzeTime: 0 };
    }
  };

  const handleSubmit = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    
    if (isSubmitting.current) return;
    isSubmitting.current = true;
    
    let answeringTool = 'chat';
  
    if ((!input.trim() && !currentUpload) || isLoading) {
      isSubmitting.current = false;
      return;
    }
    
    const timestamp = new Date().toISOString(); // Create timestamp for user message
    const userMessage = createUserMessage(input, currentUpload || undefined, timestamp);
    
    setMessages(prev => [...prev, userMessage]);
    setIsThinking(true);
    thinkingStartTime.current = Date.now(); // Start timing
    setInput("");
    setIsLoading(true);
  
    try {
      const apiMessages = prepareApiMessages(messages, userMessage);
  
      const routerResponse = await apiRequest('router', {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: apiMessages,
          model: selectedModel,
          region: selectedRegion,
          session_id: sessionId
        }),
      });
      
      if (!routerResponse.ok) {
        throw new Error(`Router API error! status: ${routerResponse.status}`);
      }
      
      const responseData = await routerResponse.json();
      console.log("Router API response:", responseData);
      
      answeringTool = responseData.input?.answering_tool || 'chat';
      
      if (responseData.input?.session_id) {
        setSessionId(responseData.input.session_id);
      } 
      
      if (responseHandlers[answeringTool]) {
        await responseHandlers[answeringTool]({
          apiMessages,
          responseData,
          setterFunctions: {
            setMessages,
            setQueryDetails,
            setIsLoading,
            setIsThinking,
            setCurrentUpload,
            setSessionId,
            originalQuestion: input,
            selectedModel,
            selectedRegion,
          }
        });
      } else {
        throw new Error("Unexpected response type from API");
      }
      
    } catch (error) {
      console.error("Submit Error:", error);
      setMessages(prev => [...prev, createErrorMessage(new Date().toISOString())]);
      setIsThinking(false);
      thinkingStartTime.current = null;
    } finally {
      setIsLoading(false);
      if (answeringTool !== 'financial') {
        setIsThinking(false);
        thinkingStartTime.current = null;
      }
      setCurrentUpload(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = ''; 
      }
  
      setTimeout(() => {
        isSubmitting.current = false;
      }, 500);
    }
  }, [messages, input, currentUpload, isLoading, selectedModel, selectedRegion, sessionId]);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    let loadingToastRef: { dismiss: () => void } | undefined;

    if (file.type === "application/pdf") {
      loadingToastRef = toast({
        title: "Processing PDF",
        description: "Extracting text content...",
        duration: Infinity,
      });
    }

    try {
      const isImage = file.type.startsWith("image/");
      const isPDF = file.type === "application/pdf";
      let base64Data = "";
      let isText = false;

      if (isImage) {
        base64Data = await readFileAsBase64(file);
        isText = false;
      } else if (isPDF) {
        try {
          const pdfText = await readFileAsPDFText(file);
          base64Data = btoa(encodeURIComponent(pdfText));
          isText = true;
        } catch (error) {
          console.error("Failed to parse PDF:", error);
          toast({
            title: "PDF parsing failed",
            description: "Unable to extract text from the PDF",
            variant: "destructive",
          });
          return;
        }
      } else {
        try {
          const textContent = await readFileAsText(file);
          base64Data = btoa(encodeURIComponent(textContent));
          isText = true;
        } catch (error) {
          console.error("Failed to read as text:", error);
          toast({
            title: "Invalid file type",
            description: "File must be readable as text, PDF, or be an image",
            variant: "destructive",
          });
          return;
        }
      }

      setCurrentUpload({
        base64: base64Data,
        fileName: file.name,
        mediaType: isText ? "text/plain" : file.type,
        isText,
      });

      toast({
        title: "File uploaded",
        description: `${file.name} ready to analyze`,
      });
    } catch (error) {
      console.error("Error processing file:", error);
      toast({
        title: "Upload failed",
        description: "Failed to process the file",
        variant: "destructive",
      });
    } finally {
      setIsUploading(false);
      if (loadingToastRef) {
        loadingToastRef.dismiss();
        if (file.type === "application/pdf") {
          toast({
            title: "PDF Processed",
            description: "Text extracted successfully",
          });
        }
      }
    }
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (input.trim() || currentUpload) {
        const form = e.currentTarget.form;
        if (form) {
          const submitEvent = new Event("submit", {
            bubbles: true,
            cancelable: true,
          });
          form.dispatchEvent(submitEvent);
        }
      }
    }
  }, [input, currentUpload]);

  const handleInputChange = useCallback(
    (event: React.ChangeEvent<HTMLTextAreaElement>) => {
      const textarea = event.target;
      setInput(textarea.value);
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 300)}px`;
    },
    []
  );

  const handleReset = useCallback(() => {
    setMessages([]);
    setQueryDetails([]);
    setInput("");
    setCurrentUpload(null);
    setIsThinking(false);
    thinkingStartTime.current = null;
    setSessionId(undefined);
        
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    toast({
      title: "Chat Reset",
      description: "All chat history and visualizations have been cleared.",
    });
  }, []);

  return {
    messages,
    input,
    isLoading,
    isThinking,
    currentUpload,
    isUploading,
    queryDetails,
    sessionId,
    
    actions: {
      setInput,
      handleSubmit,
      handleFileSelect,
      handleKeyDown,
      handleInputChange,
      handleReset,
      setCurrentUpload,
    },
    
    fileInputRef,
  };
};
