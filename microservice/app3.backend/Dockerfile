FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev && npm cache clean --force
COPY . .
ENV PORT=8082
EXPOSE 8082
USER node
CMD ["node", "server.js"]
