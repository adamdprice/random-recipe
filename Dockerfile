# Minimal image for static site + serve
FROM node:20-alpine

WORKDIR /app

# Install only production deps (one package: serve)
COPY package.json ./
RUN npm install --omit=dev

# Copy app
COPY . .

# Railway sets PORT
EXPOSE 3000
CMD ["sh", "-c", "npx serve . -p ${PORT:-3000}"]
