FROM node:20-slim

WORKDIR /app
COPY apps/dashboard/package.json ./
RUN npm install

COPY apps/dashboard .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]
