# 1) Build stage
FROM node:18 AS build
WORKDIR /app

# Install TS 5 globally
RUN npm install -g typescript@^5

# Copy package files (lockfile optional) and install deps
COPY package*.json ./
RUN npm install

# Copy source & compile
COPY . .
RUN npm run build

# 2) Production stage
FROM node:18-slim
WORKDIR /app

# Pull in built code and modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
COPY package.json ./

CMD ["node", "dist/index.js"]
