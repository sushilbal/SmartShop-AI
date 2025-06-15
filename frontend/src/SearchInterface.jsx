import React, { useState, useEffect, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid'; // For generating UUIDs
import './SearchInterface.css'; // We'll create this for basic styling

const SESSION_ID_KEY = 'smartShopAISessionId';

function SearchInterface() {
    const [sessionId, setSessionId] = useState('');
    const [query, setQuery] = useState('');
    const [chatHistory, setChatHistory] = useState([]); // Stores { type: 'user' | 'assistant', content: any }
    const [isLoading, setIsLoading] = useState(false);
    const chatEndRef = useRef(null);

    useEffect(() => {
        // Load or generate session ID on component mount
        let storedSessionId = localStorage.getItem(SESSION_ID_KEY);
        if (!storedSessionId) {
            storedSessionId = uuidv4();
            localStorage.setItem(SESSION_ID_KEY, storedSessionId);
        }
        setSessionId(storedSessionId);
    }, []);

    useEffect(() => {
        // Scroll to bottom of chat on new message
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [chatHistory]);

    const handleSearch = async (event) => {
        event.preventDefault(); // Prevent form submission if it's in a form
        if (!query.trim() || !sessionId || isLoading) return;

        setIsLoading(true);
        const currentQuery = query;
        setChatHistory(prev => [...prev, { type: 'user', text: currentQuery }]);
        setQuery(''); // Clear input

        const payload = {
            query: currentQuery,
            session_id: sessionId,
            limit: 5 // Adjust limit as needed
        };

        try {
            const response = await fetch('/api/search/', { // Nginx proxies this
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: "Unknown server error" }));
                throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            setChatHistory(prev => [
                ...prev,
                { 
                    type: 'assistant', 
                    text: data.llm_answer || "I received a response, but no specific answer was generated.",
                    results: data.results,
                    direct_product_result: data.direct_product_result,
                    query_type: data.query_type
                }
            ]);

        } catch (error) {
            console.error("Search failed:", error);
            setChatHistory(prev => [
                ...prev,
                { type: 'assistant', text: `Sorry, an error occurred: ${error.message}` }
            ]);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="search-interface-container">
            <div className="chat-display-area">
                {chatHistory.map((entry, index) => (
                    <div key={index} className={`chat-message ${entry.type}`}>
                        <div className="message-bubble">
                            <p><strong>{entry.type === 'user' ? 'You' : 'SmartShopAI'}:</strong> {entry.text}</p>
                            {entry.type === 'assistant' && entry.results && entry.results.length > 0 && (
                                <div className="search-results-snippet">
                                    <p><em>Found {entry.results.length} related items.</em></p>
                                    {/* You can add more detailed display of results here if needed */}
                                </div>
                            )}
                            {entry.type === 'assistant' && entry.direct_product_result && (
                                <div className="direct-product-snippet">
                                    <p><em>Displaying product: {entry.direct_product_result.name}</em></p>
                                     {/* You can add more detailed display of direct product here */}
                                </div>
                            )}
                        </div>
                    </div>
                ))}
                <div ref={chatEndRef} />
            </div>
            <form onSubmit={handleSearch} className="search-input-area">
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Ask about products, reviews, or policies..."
                    disabled={isLoading}
                />
                <button type="submit" disabled={isLoading || !query.trim()}>
                    {isLoading ? 'Searching...' : 'Send'}
                </button>
            </form>
            {/* <p style={{fontSize: '0.8em', color: '#777', textAlign: 'center'}}>Session ID: {sessionId}</p> */}
        </div>
    );
}

export default SearchInterface;