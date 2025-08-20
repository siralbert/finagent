import React, { useState, useRef, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardFooter, CardTitle, CardDescription } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Paperclip, MessageCircleQuestion, ChartArea, FileInput, RefreshCw, Settings, Moon, Sun, Trash2, Mic, MicOff, Volume2 } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import FilePreview from "@/components/FilePreview";
import { MessageComponent } from "@/components/MessageComponent";
import type { Message, Model, FileUpload } from '@/types/chat';
import { useAutoScroll } from "@/hooks/useAutoScroll";
import { useTheme } from "next-themes";
import MCPServerSettings from "@/components/MCPServerSettings";

interface ChatProps {
  messages: Message[];
  input: string;
  isLoading: boolean;
  currentUpload: FileUpload | null;
  selectedModel: string;
  selectedRegion: string;
  models: Model[];
  regions: { id: string; name: string }[];
  isThinking: boolean;
  fileInputRef: React.RefObject<HTMLInputElement>;
  onInputChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  setSelectedModel: (modelId: string) => void;
  setSelectedRegion: (regionId: string) => void;
  setCurrentUpload: (upload: FileUpload | null) => void;
  onReset?: () => void;
}

// Voice Input Hook
const useVoiceInput = (onTranscriptionComplete: (text: string) => void) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [error, setError] = useState('');
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const cleanup = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const startRecording = useCallback(async () => {
    try {
      setError('');
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 44100,
        }
      });
      
      streamRef.current = stream;
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });
      
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm;codecs=opus' });
        await transcribeAudio(audioBlob);
        cleanup();
      };

      mediaRecorder.start(100); // Collect data every 100ms
      setIsRecording(true);
    } catch (err) {
      console.error('Microphone access error:', err);
      if (err instanceof Error) {
        if (err.name === 'NotAllowedError') {
          setError('Microphone permission denied. Please enable microphone access.');
        } else if (err.name === 'NotFoundError') {
          setError('No microphone found. Please connect a microphone.');
        } else {
          setError('Failed to access microphone. Please check your settings.');
        }
      }
    }
  }, [cleanup]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  }, []);

// Enhanced transcribeAudio function with better error handling and user feedback
const transcribeAudio = async (audioBlob: Blob) => {
  setIsTranscribing(true);
  setError(''); // Clear any previous errors
  
  try {
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.webm');

    const response = await fetch('http://localhost:8000/api/transcribe', {
      method: 'POST',
      body: formData,
      mode: 'cors',
    });

    if (response.ok) {
      const result = await response.json();
      const transcribedText = result.text || result.transcription || '';
      
      if (transcribedText.trim()) {
        onTranscriptionComplete(transcribedText);
      } else {
        setError('No speech detected. Please try speaking more clearly.');
      }
    } else {
      let errorMessage = `Transcription failed: ${response.status}`;
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorData.error || errorMessage;
      } catch {
        const errorText = await response.text();
        errorMessage = errorText || errorMessage;
      }
      throw new Error(errorMessage);
    }
  } catch (error) {
    console.error('Transcription error:', error);
    
    if (error instanceof TypeError && error.message.includes('fetch')) {
      setError('Cannot connect to transcription service. Make sure the Python backend is running.');
    } else if (error instanceof Error) {
      setError(error.message);
    } else {
      setError('Failed to transcribe audio. Please try again.');
    }
  } finally {
    setIsTranscribing(false);
  }
};

// Enhanced UI feedback for transcription status
{(isRecording || isTranscribing) && (
  <div className="flex items-center justify-between p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
    <div className="flex items-center space-x-2 text-blue-700 dark:text-blue-300">
      {isRecording && (
        <>
          <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
          <span className="text-sm font-medium">🎤 Recording... Click mic to stop</span>
        </>
      )}
      {isTranscribing && (
        <>
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <span className="text-sm font-medium">🔄 Converting speech to text...</span>
        </>
      )}
    </div>
    {isRecording && (
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={stopRecording}
        className="text-xs"
      >
        Stop
      </Button>
    )}
  </div>
)}

// Add a success indicator when transcription completes
{/* You can add this as a state variable and show it briefly after successful transcription */}


  return {
    isRecording,
    isTranscribing,
    error,
    startRecording,
    stopRecording,
    cleanup,
    setError
  };
};

const ThinkingIndicator: React.FC = () => {
    return (
      <div className="flex flex-col space-y-3 p-4 bg-gradient-to-r from-blue-50 via-gray-50 to-gray-100 dark:from-blue-950/30 dark:via-gray-800/80 dark:to-gray-900 rounded-lg border border-blue-100 dark:border-blue-900/50 shadow-soft animate-expand-in">
        <div className="flex items-center justify-between">
          <div className="text-gray-700 dark:text-gray-200 font-medium flex items-center">
            <div className="relative mr-3">
              <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin"></div>
              <div className="absolute top-1/2 left-1/2 w-2 h-2 bg-primary rounded-full transform -translate-x-1/2 -translate-y-1/2"></div>
            </div>
            <span className="font-semibold">Analyzing data...</span>
          </div>
        </div>
        
        <div className="space-y-2">
          <div className="h-2 bg-gray-200 dark:bg-gray-600 rounded-full w-3/4 animate-pulse"></div>
          <div className="h-2 bg-gray-200 dark:bg-gray-600 rounded-full w-1/2 animate-pulse"></div>
          <div className="h-2 bg-gray-200 dark:bg-gray-600 rounded-full w-5/6 animate-pulse"></div>
        </div>
      </div>
    );
  };   

const Chat: React.FC<ChatProps> = ({
  messages,
  input,
  isLoading,
  currentUpload,
  selectedModel,
  selectedRegion,
  models,
  regions,
  isThinking,
  fileInputRef,  
  onInputChange,
  onKeyDown,
  onSubmit,
  onFileSelect,
  setSelectedModel,
  setSelectedRegion,
  setCurrentUpload,
  onReset,
}) => {
  // Auto-scroll when messages change or thinking status changes
  const messagesEndRef = useAutoScroll([messages, isLoading, isThinking]);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const { theme, setTheme } = useTheme();

  const [transcriptionSuccess, setTranscriptionSuccess] = useState(false);

  
// Enhanced handleVoiceTranscription function with better user experience
const handleVoiceTranscription = useCallback((transcribedText: string) => {
  if (!transcribedText.trim()) return;
  
  // Clean up the transcribed text
  const cleanedText = transcribedText.trim();
  
  // Determine how to add the text based on current input
  let newInputValue: string;
  
  if (!input.trim()) {
    // If input is empty, just add the transcribed text
    newInputValue = cleanedText;
  } else {
    // If there's existing text, add a space and then the transcribed text
    newInputValue = input.trim() + ' ' + cleanedText;
  }
  
  // Create a synthetic event to update the input
  const syntheticEvent = {
    target: { value: newInputValue }
  } as React.ChangeEvent<HTMLTextAreaElement>;
  
  onInputChange(syntheticEvent);
  
  // Optional: Focus the textarea after transcription
  setTimeout(() => {
    const textarea = document.querySelector('textarea');
    if (textarea) {
      textarea.focus();
      // Position cursor at the end
      textarea.setSelectionRange(newInputValue.length, newInputValue.length);
    }
  }, 100);

  // Show success indicator briefly
  setTranscriptionSuccess(true);
  setTimeout(() => setTranscriptionSuccess(false), 2000);
}, [input, onInputChange]);

  const {
    isRecording,
    isTranscribing,
    error: voiceError,
    startRecording,
    stopRecording,
    setError: setVoiceError
  } = useVoiceInput(handleVoiceTranscription);
  
  // Function to open MCP settings modal
  const onMCPSettingsOpen = () => setIsSettingsOpen(true);

  // Handle microphone button click
  const handleMicClick = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  return (
    <Card className="w-full lg:w-3/5 xl:w-2/3 md:w-3/5 flex flex-col h-full shadow-sm border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
      <CardHeader className="py-3 px-5 border-b border-gray-100 dark:border-gray-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            {messages.length > 0 && (
              <>
                <Avatar className="w-8 h-8">
                  <AvatarImage src="/bedrock-logo.png" alt="AI Assistant Avatar" />
                  <AvatarFallback>AI</AvatarFallback>
                </Avatar>
                <div>
                  <CardTitle className="text-base">Assistant</CardTitle>
                  <CardDescription className="text-xs">Powered by Bedrock</CardDescription>
                </div>
              </>
            )}
          </div>
          <div className="flex items-center space-x-2">
            <div className="w-px h-5 bg-gray-200 dark:bg-gray-700 mx-1 hidden"></div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="h-8 text-sm">
                  {regions.find((r) => r.id === selectedRegion)?.name}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                {regions.map((region) => (
                  <DropdownMenuItem key={region.id} onSelect={() => setSelectedRegion(region.id)}>
                    {region.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="h-8 text-sm">
                  {models.find((m) => m.id === selectedModel)?.name}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                {models.map((model) => (
                  <DropdownMenuItem key={model.id} onSelect={() => setSelectedModel(model.id)}>
                    {model.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            
            <Button
              variant="outline"
              size="sm"
              onClick={onMCPSettingsOpen}
              title="MCP Server Settings"
              className="h-8 text-xs flex gap-1 items-center">
              <Settings className="h-3.5 w-3.5" />
              <span>Tool</span>
            </Button>
            
            {/* Theme button moved from footer to header */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="h-8 text-xs flex gap-1 items-center">
                  <div className="relative flex items-center justify-center w-3.5 h-3.5">
                    <Sun className="h-3.5 w-3.5 absolute rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
                    <Moon className="h-3.5 w-3.5 absolute rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
                  </div>
                  <span>Theme</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setTheme("light")}>
                  Light
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setTheme("dark")}>
                  Dark
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setTheme("system")}>
                  System
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            
            {/* Clear Chat button moved from footer to header */}
            <Button
              variant="outline"
              size="sm"
              onClick={onReset}
              className="h-8 text-xs flex gap-1 items-center"
              title="Reset Chat"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span>Clear Chat</span>
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-y-auto p-5 scroll-smooth">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full animate-fade-in-up max-w-md mx-auto">
            <div className="relative mb-6 group">
              <div className="absolute -inset-1 bg-gradient-to-r from-primary to-blue-600 rounded-full opacity-75 blur-sm group-hover:opacity-100 transition duration-500 group-hover:duration-200"></div>
              <Avatar className="w-16 h-16 relative">
                <AvatarImage src="/bedrock-logo.png" alt="AI Assistant Avatar" width={64} height={64} className="animate-pulse-subtle" />
              </Avatar>
            </div>
            <h2 className="text-2xl font-medium mb-2 text-gray-900 dark:text-gray-50 tracking-tight heading-font animate-fade-in">Financial Assistant</h2>
            <p className="text-gray-500 dark:text-gray-400 mb-10 text-center animate-fade-in delay-100">Analyze financial data and answer market questions.</p>
            
            <div className="grid grid-cols-1 gap-5 w-full">
              <div className="flex items-center gap-4 p-4 bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-800/20 dark:to-gray-900/40 rounded-xl border border-gray-100 dark:border-gray-800 hover-lift shadow-soft animate-fade-in delay-100">
                <div className="w-10 h-10 flex items-center justify-center rounded-full bg-blue-50 dark:bg-blue-900/30">
                  <MessageCircleQuestion className="text-blue-500 dark:text-blue-400 w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-50 mb-1">Market Analysis</h3>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">Ask about stocks, trends, and financial performance.</p>
                </div>
              </div>
              
              <div className="flex items-center gap-4 p-4 bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-800/20 dark:to-gray-900/40 rounded-xl border border-gray-100 dark:border-gray-800 hover-lift shadow-soft animate-fade-in delay-200">
                <div className="w-10 h-10 flex items-center justify-center rounded-full bg-green-50 dark:bg-green-900/30">
                  <ChartArea className="text-green-500 dark:text-green-400 w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-50 mb-1">Data Visualization</h3>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">Generate charts from your financial data.</p>
                </div>
              </div>
              
              <div className="flex items-center gap-4 p-4 bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-800/20 dark:to-gray-900/40 rounded-xl border border-gray-100 dark:border-gray-800 hover-lift shadow-soft animate-fade-in delay-300">
                <div className="w-10 h-10 flex items-center justify-center rounded-full bg-purple-50 dark:bg-purple-900/30">
                  <FileInput className="text-purple-500 dark:text-purple-400 w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-50 mb-1">File Analysis</h3>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">Upload CSVs, PDFs, or images for analysis.</p>
                </div>
              </div>
              
              <div className="flex items-center gap-4 p-4 bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-800/20 dark:to-gray-900/40 rounded-xl border border-gray-100 dark:border-gray-800 hover-lift shadow-soft animate-fade-in delay-300">
                <div className="w-10 h-10 flex items-center justify-center rounded-full bg-red-50 dark:bg-red-900/30">
                  <Volume2 className="text-red-500 dark:text-red-400 w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-50 mb-1">Voice Input</h3>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">Use the microphone button to speak your questions.</p>
                </div>
              </div>
            </div>
            
            <div className="mt-10 text-sm text-gray-400 dark:text-gray-500 text-center">
              Tip: Be specific with your financial questions for better results.
            </div>
          </div>
        ) : (
          <div className="space-y-4 min-h-full">
            {messages.map((message) => (
              <div key={message.id}>
                <MessageComponent message={message} />
              </div>
            ))}
            {isThinking && (
              <div className="animate-fade-in-up">
                <ThinkingIndicator />
              </div>
            )}
            <div ref={messagesEndRef} className="h-4" />
          </div>
        )}
      </CardContent>

      <CardFooter className="p-4 border-t border-gray-100 dark:border-gray-800">
        <form onSubmit={onSubmit} className="w-full">
          <div className="flex flex-col space-y-2">
            {/* Voice Error Display */}
            {voiceError && (
              <div className="flex items-center justify-between p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300 text-sm">
                <span>{voiceError}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setVoiceError('')}
                  className="h-6 w-6 p-0 text-red-500 hover:text-red-600"
                >
                  ×
                </Button>
              </div>
            )}
            
            {/* Voice Recording Indicator */}
            {(isRecording || isTranscribing) && (
              <div className="flex items-center justify-center p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                <div className="flex items-center space-x-2 text-blue-700 dark:text-blue-300">
                  {isRecording && (
                    <>
                      <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
                      <span className="text-sm font-medium">Recording... Click mic to stop</span>
                    </>
                  )}
                  {isTranscribing && (
                    <>
                      <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                      <span className="text-sm font-medium">Converting speech to text...</span>
                    </>
                  )}
                </div>
              </div>
            )}

		{transcriptionSuccess && (
		  <div className="flex items-center justify-center p-2 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
		    <div className="flex items-center space-x-2 text-green-700 dark:text-green-300">
		      <div className="w-2 h-2 bg-green-500 rounded-full"></div>
		      <span className="text-sm">✅ Speech transcribed! Review and edit if needed.</span>
		    </div>
		  </div>
		)}

            {currentUpload && (
              <FilePreview file={currentUpload} onRemove={() => setCurrentUpload(null)} />
            )}
            <div className="flex items-end space-x-2">
              <div className="flex-1 relative">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isLoading}
                  className="absolute left-2 top-1/2 -translate-y-1/2 h-8 w-8 text-gray-500"
                >
                  <Paperclip className="h-5 w-5" />
                </Button>
                <Textarea
                  value={input}
                  onChange={onInputChange}
                  onKeyDown={onKeyDown}
                  placeholder="Ask about stocks, markets, or upload financial data..."
                  disabled={isLoading}
                  className="min-h-[48px] h-[48px] resize-none pl-12 pr-12 py-3 flex items-center rounded-lg border-gray-300 dark:border-gray-700"
                  rows={1}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={handleMicClick}
                  disabled={isLoading || isTranscribing}
                  className={`absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 transition-colors ${
                    isRecording 
                      ? 'text-red-500 hover:text-red-600 bg-red-50 dark:bg-red-900/20' 
                      : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                  }`}
                  title={isRecording ? 'Stop recording' : 'Start voice input'}
                >
                  {isRecording ? (
                    <MicOff className="h-5 w-5" />
                  ) : (
                    <Mic className="h-5 w-5" />
                  )}
                </Button>
              </div>
              <Button 
                type="submit" 
                disabled={isLoading || isThinking || (!input.trim() && !currentUpload)} 
                className="h-[48px] btn-hover bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 dark:from-blue-600 dark:to-blue-700 dark:hover:from-blue-700 dark:hover:to-blue-800 text-white px-5 rounded-lg shadow-md hover:shadow-lg transition-all duration-300"
              >
                <Send className="h-4 w-4 mr-1" />
                <span className="hidden sm:inline">Send</span>
              </Button>
            </div>
          </div>
          <div className="flex justify-end mt-2 text-xs text-gray-400 dark:text-gray-500">
            <div className="flex items-center space-x-3">
              <span><kbd className="px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500">Enter</kbd> Send</span>
              <span><kbd className="px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500">Shift+Enter</kbd> New line</span>
              <span><kbd className="px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500">🎤</kbd> Voice input</span>
            </div>
          </div>
          <input type="file" ref={fileInputRef} className="hidden" onChange={onFileSelect} />
        </form>
      </CardFooter>
      
      {/* MCP Settings Modal */}
      <MCPServerSettings 
        isOpen={isSettingsOpen} 
        onClose={() => setIsSettingsOpen(false)} 
      />
    </Card>
  );
};

export default Chat;
