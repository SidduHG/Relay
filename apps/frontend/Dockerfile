FROM node:20-slim

WORKDIR /app
COPY apps/frontend/package.json ./
RUN npm install

COPY apps/frontend .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]
