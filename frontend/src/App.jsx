import React from 'react';
import { useState } from 'react';
import axios from 'axios';
import './App.css';

// The backend URL is now relative, so it will use the same host as the frontend
const API_BASE_URL = '/api';

function App() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) {
      setError('Please enter a search query.');
      return;
    }
    setLoading(true);
    setError('');
    setResults(null);

    try {
      // The URL now correctly points to the Nginx proxy route
      const response = await axios.post(`${API_BASE_URL}/search/`, {
        query: query,
        limit: 10,
      });
      setResults(response.data);
    } catch (err) {
      setError('Error: Could not connect to the backend. Please ensure all services are running and check the browser console for more details.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const renderResults = () => {
    if (!results) return null;

    return (
        <div className="results-container">
            {results.llm_answer && (
                <div className="result-card ai-answer">
                    <h3>🤖 AI Assistant's Answer</h3>
                    <p>{results.llm_answer}</p>
                </div>
            )}

            {results.direct_product_result && (
                <div className="result-card product-direct">
                    <h3>🎯 Direct Product Match</h3>
                    <h4>{results.direct_product_result.name}</h4>
                    <p><strong>Brand:</strong> {results.direct_product_result.brand}</p>
                    <p><strong>Price:</strong> ${results.direct_product_result.price.toFixed(2)}</p>
                    <p>{results.direct_product_result.description}</p>
                </div>
            )}

            {results.results?.length > 0 && (
                 <div className="retrieved-docs">
                    <h3>📚 Retrieved Source Documents</h3>
                    {results.results.map((item, index) => (
                        <div key={index} className="result-card doc-snippet">
                           <p><strong>Source:</strong> {item.source_collection}</p>
                           <p><strong>Snippet:</strong> {item.payload?.chunk_text || item.payload?.text_chunk || 'N/A'}</p>
                           <p className="score">Relevance Score: {item.score.toFixed(4)}</p>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
  }

  return (
    <div className="App">
      <header className="App-header">
        <h1>🛍️ SmartShop AI</h1>
        <p>A scalable, AI-powered e-commerce search experience.</p>
      </header>
      <main>
        <form onSubmit={handleSearch} className="search-form">
          <input
            type="text"
            className="search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="What can I help you find today?"
            disabled={loading}
          />
          <button type="submit" className="search-button" disabled={loading}>
            {loading ? 'Searching...' : 'Search'}
          </button>
        </form>

        {error && <p className="error">{error}</p>}
        {loading && <div className="loader"></div>}

        {results && renderResults()}
      </main>
    </div>
  );
}

export default App;