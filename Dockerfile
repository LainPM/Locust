# Build stage
FROM node:18 AS build

# Set working directory
WORKDIR /app

# Install TypeScript 5 globally
RUN npm install -g typescript@^5

# Copy package files and install project dependencies
COPY package.json package-lock.json ./
RUN npm install

# Copy all other source code
COPY . .

# Build the TypeScript project
RUN npm run build

# Final stage: running container
FROM node:18-slim

# Set working directory
WORKDIR /app

# Copy compiled code and node_modules from build stage
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
COPY package.json ./

# Command to run your bot
CMD ["node", "dist/index.js"]
