# ---- Stage 1: Build the React application ----
FROM node:18-alpine AS builder

WORKDIR /app

COPY package*.json ./

RUN npm install


COPY . .

# Run the build and then list the contents to verify
RUN npm run build


# ---- Debug: List contents of /app/dist in the builder stage ----
RUN echo "Listing contents of /app/dist after build:" && ls -lA /app/dist
RUN echo "Listing contents of /app/dist/assets (if it exists):" && (ls -lA /app/dist/assets || echo "/app/dist/assets directory not found")


# ---- Stage 2: Serve the application with Nginx ----
FROM nginx:1.25-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]